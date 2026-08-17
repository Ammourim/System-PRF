"""Tela HOJE: objetivos do dia, registro de estudo e conclusao de assunto.

Estes testes fixam a filosofia do sistema simplificado:
  * abrir a tela nao cria nada;
  * registrar estudo NAO conclui o assunto;
  * concluir o assunto e o que inicia a revisao espacada;
  * nao estudar hoje nao gera pendencia nenhuma.
"""

from app.db import query_one, scalar
from app.services import today as today_service
from app.utils import add_days, today_iso


# --------------------------------------------------------------------------
# Escolha das disciplinas do dia
# --------------------------------------------------------------------------
def test_frequencia_padrao_vem_da_prioridade():
    assert today_service.default_frequency("maxima") == 5
    assert today_service.default_frequency("alta") == 3
    assert today_service.default_frequency("media") == 2
    assert today_service.default_frequency("baixa") == 1


def test_frequencia_f_aparece_f_dias_em_cada_semana():
    for frequency in range(1, 8):
        for offset in range(0, 7):
            dias = sum(1 for d in range(738000, 738007)
                       if today_service.lands_on(d, frequency, offset))
            assert dias == frequency, (frequency, offset)


def test_lista_do_dia_e_deterministica(ctx):
    primeira = [d["id"] for d in today_service.objectives("2026-08-17")]
    segunda = [d["id"] for d in today_service.objectives("2026-08-17")]
    assert primeira == segunda


def test_prioridade_maxima_aparece_mais_que_baixa(ctx):
    ctx.execute("UPDATE disciplines SET active = 0")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'maxima', frequency = 5"
                " WHERE id = 1")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'baixa', frequency = 1"
                " WHERE id = 2")
    ctx.commit()

    base = today_iso()
    maxima = baixa = 0
    for n in range(14):
        # Dias de "fallback" (nenhuma disciplina sorteada) nao contam: ali o
        # sistema apenas evita uma tela vazia.
        for item in today_service.objectives(add_days(base, n)):
            if item["fallback"]:
                continue
            maxima += item["id"] == 1
            baixa += item["id"] == 2
    assert maxima == 10 and baixa == 2


def test_disciplina_inativa_nunca_aparece(ctx):
    ctx.execute("UPDATE disciplines SET active = 0 WHERE id = 1")
    ctx.commit()
    for n in range(14):
        ids = [d["id"] for d in today_service.objectives(add_days(today_iso(), n))]
        assert 1 not in ids


def test_teto_de_disciplinas_por_dia(ctx):
    from app.services import settings as settings_service

    settings_service.set_value("today_max_disciplines", 2)
    assert len(today_service.objectives()) <= 2


# --------------------------------------------------------------------------
# Registro de estudo
# --------------------------------------------------------------------------
def test_registrar_estudo_nao_conclui_o_assunto(client, app):
    client.post("/estudar", data={
        "discipline_id": "1", "subject_name": "Infracoes de transito", "minutes": "40",
    }, follow_redirects=True)

    with app.app_context():
        subject = query_one("SELECT * FROM subjects WHERE name = 'Infracoes de transito'")
        assert subject["status"] == "em_andamento"
        assert subject["completed_at"] is None
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0


def test_estudo_sem_tempo_e_aceito(client, app):
    """O sistema funciona se voce estudou 6 horas ou nao anotou o tempo."""
    client.post("/estudar", data={
        "discipline_id": "1", "subject_name": "Sinalizacao",
    }, follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM study_sessions ORDER BY id DESC LIMIT 1")
        assert row["actual_minutes"] == 0
        assert row["subject_id"] is not None


def test_mesmo_assunto_em_dias_diferentes_nao_duplica_o_assunto(client, app):
    for dia in [add_days(today_iso(), -2), add_days(today_iso(), -1), today_iso()]:
        client.post("/estudar", data={
            "discipline_id": "1", "subject_name": "Infracoes", "date": dia,
        }, follow_redirects=True)

    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM subjects WHERE lower(name) = 'infracoes'", (), 0) == 1
        assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 3


def test_questoes_ficam_apenas_registradas(client, app):
    client.post("/estudar", data={
        "discipline_id": "1", "subject_name": "Placas", "minutes": "30",
        "questions_total": "20", "questions_correct": "15",
    }, follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
        assert row["total"] == 20 and row["correct"] == 15 and row["percentage"] == 75.0
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0  # nao mexe na revisao


# --------------------------------------------------------------------------
# Conclusao do assunto -> revisao espacada
# --------------------------------------------------------------------------
def _subject(client, app, name="Infracoes"):
    client.post("/estudar", data={"discipline_id": "1", "subject_name": name},
                follow_redirects=True)
    with app.app_context():
        return query_one("SELECT id FROM subjects WHERE name = ?", (name,))["id"]


def test_concluir_assunto_pergunta_antes_de_agendar(client, app):
    subject_id = _subject(client, app)
    resposta = client.post(f"/assunto/{subject_id}/concluir", follow_redirects=True)
    corpo = resposta.get_data(as_text=True)
    assert "Deseja agendar as revisoes espacadas?" in corpo

    with app.app_context():
        assert query_one("SELECT * FROM subjects WHERE id = ?",
                         (subject_id,))["status"] == "concluida"
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0  # ainda nao respondeu


def test_responder_sim_cria_a_sequencia(client, app):
    subject_id = _subject(client, app)
    client.post(f"/assunto/{subject_id}/concluir", follow_redirects=True)
    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "1"},
                follow_redirects=True)

    with app.app_context():
        review = query_one("SELECT * FROM reviews ORDER BY id DESC LIMIT 1")
        assert review["subject_id"] == subject_id
        assert review["interval_days"] == 1
        assert review["next_date"] == add_days(today_iso(), 1)
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 1


def test_responder_nao_nao_cria_revisao(client, app):
    subject_id = _subject(client, app)
    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "0"},
                follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0


def test_concluir_duas_vezes_nao_duplica_revisao(client, app):
    subject_id = _subject(client, app)
    for _ in range(3):
        client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "1"},
                    follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 1


def test_reabrir_assunto_volta_para_em_andamento(client, app):
    subject_id = _subject(client, app)
    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "0"},
                follow_redirects=True)
    client.post(f"/assunto/{subject_id}/reabrir", follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM subjects WHERE id = ?", (subject_id,))
        assert row["status"] == "em_andamento" and row["completed_at"] is None


# --------------------------------------------------------------------------
# Sem punicao
# --------------------------------------------------------------------------
def test_nao_estudar_nao_gera_pendencia(client, app):
    """Nenhuma tarefa e criada por causa de um dia sem estudo."""
    with app.app_context():
        antes = (scalar("SELECT COUNT(*) FROM study_sessions", (), 0),
                 scalar("SELECT COUNT(*) FROM reviews", (), 0))

    for _ in range(5):
        assert client.get("/").status_code == 200

    with app.app_context():
        assert (scalar("SELECT COUNT(*) FROM study_sessions", (), 0),
                scalar("SELECT COUNT(*) FROM reviews", (), 0)) == antes


def test_fluxo_completo_do_usuario(client, app):
    """Estudar 3 dias -> terminar -> agendar -> revisar D1 -> proxima e D7."""
    for dia in [add_days(today_iso(), -2), add_days(today_iso(), -1), today_iso()]:
        client.post("/estudar", data={
            "discipline_id": "1", "subject_name": "Infracoes de transito", "date": dia,
            "minutes": "45"}, follow_redirects=True)

    with app.app_context():
        subject_id = query_one(
            "SELECT id FROM subjects WHERE name = 'Infracoes de transito'")["id"]

    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "1"},
                follow_redirects=True)
    with app.app_context():
        review = query_one("SELECT * FROM reviews ORDER BY id DESC LIMIT 1")
        review_id, next_date = review["id"], review["next_date"]

    # A revisao D1 aparece na fila no dia previsto.
    with app.app_context():
        from app.services import reviews as reviews_service
        fila = reviews_service.due(next_date)
        assert [r["id"] for r in fila] == [review_id]
        assert fila[0]["label"] == "D1"

    client.post(f"/revisoes/{review_id}/concluir", data={"done_date": next_date},
                follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
        assert row["interval_days"] == 7
        assert row["next_date"] == add_days(next_date, 7)
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 1


def test_tela_de_disciplinas_salva_prioridade_frequencia_e_ativa(client, app):
    """As tres unicas decisoes da tela de Disciplinas gravam de verdade."""
    client.post("/disciplinas/pesos", data={
        "today_max_disciplines": "3",
        "row_1": "1", "priority_1": "baixa", "frequency_1": "2", "active_1": "1",
        "row_2": "1", "priority_2": "maxima", "frequency_2": "7",  # sem active = inativa
    }, follow_redirects=True)

    with app.app_context():
        from app.services import settings as settings_service

        um = query_one("SELECT * FROM disciplines WHERE id = 1")
        dois = query_one("SELECT * FROM disciplines WHERE id = 2")
        assert um["priority"] == "baixa" and um["frequency"] == 2 and um["active"] == 1
        assert dois["frequency"] == 7 and dois["active"] == 0
        assert settings_service.get_int("today_max_disciplines") == 3
        assert 2 not in [d["id"] for d in today_service.objectives()]
