"""Testes da revisao espacada."""

from app.db import query_one
from app.services import reviews as reviews_service
from app.services import settings as settings_service
from app.services import stats as stats_service
from app.services import subjects as subjects_service
from app.utils import add_days, today_iso


def test_criar_revisao_usa_primeiro_intervalo(ctx):
    review_id = reviews_service.create_review(discipline_id=1, title="Infracoes")
    row = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    assert row["step"] == 0
    assert row["interval_days"] == 1
    assert row["next_date"] == add_days(today_iso(), 1)
    assert row["status"] == "pendente"


def test_concluir_avanca_para_o_proximo_intervalo(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    result = reviews_service.complete_review(review_id, difficulty="media")
    assert result["step"] == 1
    assert result["interval_days"] == 7  # intervalos padrao: 1,7,15,30,60
    row = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    assert row["times_done"] == 1
    assert row["next_date"] == add_days(today_iso(), 7)


def test_nada_altera_o_intervalo_da_lista(ctx):
    """Sem algoritmo: o intervalo e o da lista, aconteca o que acontecer."""
    facil = reviews_service.create_review(discipline_id=1)
    dificil = reviews_service.create_review(discipline_id=1)
    r_facil = reviews_service.complete_review(facil, difficulty="facil")
    r_dificil = reviews_service.complete_review(dificil, difficulty="dificil")
    assert r_facil["interval_days"] == 7
    assert r_dificil["interval_days"] == 7


def test_proxima_data_sai_da_conclusao_real_nao_da_prevista(ctx):
    """Revisao atrasada: conta a partir do dia em que voce realmente fez."""
    review_id = reviews_service.create_review(discipline_id=1)
    ctx.execute("UPDATE reviews SET next_date = ? WHERE id = ?",
                (add_days(today_iso(), -5), review_id))
    ctx.commit()

    feito_em = add_days(today_iso(), -2)
    result = reviews_service.complete_review(review_id, done_date=feito_em)
    assert result["next_date"] == add_days(feito_em, 7)
    assert query_one("SELECT COUNT(*) AS n FROM reviews", ())["n"] == 1  # nada duplicado


def test_sequencia_termina_no_ultimo_intervalo(ctx):
    """D1, D7, D15, D30, D60 e acabou - o sistema nao inventa revisao infinita."""
    review_id = reviews_service.create_review(discipline_id=1)
    for esperado in [7, 15, 30, 60]:
        assert reviews_service.complete_review(review_id)["interval_days"] == esperado

    final = reviews_service.complete_review(review_id)
    assert final["finished"] is True
    row = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    assert row["status"] == "concluida"
    assert row["times_done"] == 5
    assert reviews_service.counts()["due"] == 0


def test_concluir_assunto_nao_duplica_a_fila(ctx):
    subject_id = ctx.execute(
        "INSERT INTO subjects (discipline_id, name, status) VALUES (1, 'Infracoes', 'concluida')"
    ).lastrowid
    ctx.commit()
    primeiro = reviews_service.create_for_subject(1, subject_id, title="Infracoes")
    segundo = reviews_service.create_for_subject(1, subject_id, title="Infracoes")
    assert primeiro is not None
    assert segundo is None
    assert query_one("SELECT COUNT(*) AS n FROM reviews", ())["n"] == 1


def test_rotulo_da_revisao_e_o_intervalo(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    assert reviews_service.get(review_id)["label"] == "D1"
    reviews_service.complete_review(review_id)
    assert reviews_service.get(review_id)["label"] == "D7"


def test_intervalos_configuraveis(ctx):
    settings_service.set_value("review_intervals", "2, 5, 10")
    assert reviews_service.intervals() == [2, 5, 10]
    review_id = reviews_service.create_review(discipline_id=1)
    assert query_one("SELECT interval_days FROM reviews WHERE id = ?",
                     (review_id,))["interval_days"] == 2


def test_fila_separa_vencidas_e_futuras(ctx):
    atrasada = reviews_service.create_review(discipline_id=1, title="Atrasada")
    ctx.execute("UPDATE reviews SET next_date = ? WHERE id = ?",
                (add_days(today_iso(), -3), atrasada))
    hoje = reviews_service.create_review(discipline_id=1, title="Hoje")
    ctx.execute("UPDATE reviews SET next_date = ? WHERE id = ?", (today_iso(), hoje))
    reviews_service.create_review(discipline_id=1, title="Futura")
    ctx.commit()

    due = reviews_service.due()
    titles = {r["title"] for r in due}
    assert titles == {"Atrasada", "Hoje"}
    assert {r["urgency"] for r in due} == {"atrasada", "hoje"}

    counts = reviews_service.counts()
    assert counts["due"] == 2 and counts["late"] == 1 and counts["total"] == 3


def test_adiar_e_arquivar(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    reviews_service.snooze(review_id, 3)
    row = query_one("SELECT next_date FROM reviews WHERE id = ?", (review_id,))
    assert row["next_date"] == add_days(add_days(today_iso(), 1), 3)

    reviews_service.archive(review_id)
    assert query_one("SELECT status FROM reviews WHERE id = ?", (review_id,))["status"] \
        == "arquivada"
    assert reviews_service.counts()["due"] == 0

    reviews_service.reactivate(review_id)
    assert query_one("SELECT next_date FROM reviews WHERE id = ?",
                     (review_id,))["next_date"] == today_iso()


# --------------------------------------------------------------------------
# Questoes feitas dentro da revisao
# --------------------------------------------------------------------------
def test_questoes_da_revisao_viram_registro_de_questoes(ctx):
    """Revisar fazendo questoes alimenta a tabela que o desempenho ja usa."""
    subject_id = subjects_service.resolve(1, "Infracoes")
    review_id = reviews_service.create_review(discipline_id=1, subject_id=subject_id,
                                              title="Infracoes")
    result = reviews_service.complete_review(review_id, questions_total=20,
                                             questions_correct=15)

    assert result["questions"] == 20
    assert result["accuracy"] == 75.0

    registro = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
    assert registro["kind"] == "revisao"
    assert registro["discipline_id"] == 1
    assert registro["subject_id"] == subject_id
    assert (registro["total"], registro["correct"], registro["wrong"]) == (20, 15, 5)
    assert registro["percentage"] == 75.0
    assert registro["date"] == today_iso()
    assert registro["source"] == "Revisao D1"


def test_questoes_da_revisao_entram_no_desempenho(ctx):
    subject_id = subjects_service.resolve(1, "Infracoes")
    review_id = reviews_service.create_review(discipline_id=1, subject_id=subject_id)
    reviews_service.complete_review(review_id, questions_total=10, questions_correct=6)

    geral = stats_service.overall(days=30)
    assert geral["questions"] == 10
    assert geral["correct"] == 6
    assert geral["accuracy"] == 60.0

    por_assunto = {r["subject_name"]: r for r in stats_service.by_subject(days=30)}
    assert por_assunto["Infracoes"]["accuracy"] == 60.0


def test_questoes_acumulam_na_fila_da_revisao(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    reviews_service.complete_review(review_id, questions_total=10, questions_correct=5)
    reviews_service.complete_review(review_id, questions_total=10, questions_correct=9)

    row = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    assert (row["questions_total"], row["questions_correct"]) == (20, 14)
    assert reviews_service.get(review_id)["accuracy"] == 70.0


def test_revisao_sem_questoes_continua_valendo(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    result = reviews_service.complete_review(review_id)

    assert result["step"] == 1
    assert result["questions"] == 0
    assert result["accuracy"] is None
    assert query_one("SELECT COUNT(*) AS n FROM questions")["n"] == 0
    assert query_one("SELECT questions_total AS t FROM reviews WHERE id = ?",
                     (review_id,))["t"] == 0


def test_acertos_nao_passam_do_total(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    reviews_service.complete_review(review_id, questions_total=10, questions_correct=30)
    registro = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
    assert (registro["correct"], registro["wrong"]) == (10, 0)


def test_concluir_pela_tela_da_revisao_registra_questoes(client):
    with client.application.app_context():
        subject_id = subjects_service.resolve(1, "Placas")
        review_id = reviews_service.create_review(discipline_id=1, subject_id=subject_id)

    client.post(f"/revisoes/{review_id}/concluir",
                data={"done_date": today_iso(), "questions_total": "25",
                      "questions_correct": "20"})

    with client.application.app_context():
        registro = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
        assert (registro["total"], registro["correct"]) == (25, 20)
        assert registro["kind"] == "revisao"
