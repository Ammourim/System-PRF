"""Testes da revisao espacada."""

from app.db import query_one
from app.services import reviews as reviews_service
from app.services import settings as settings_service
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


def test_dificuldade_encurta_ou_alonga(ctx):
    facil = reviews_service.create_review(discipline_id=1)
    dificil = reviews_service.create_review(discipline_id=1)
    r_facil = reviews_service.complete_review(facil, difficulty="facil")
    r_dificil = reviews_service.complete_review(dificil, difficulty="dificil")
    assert r_facil["interval_days"] == round(7 * 1.5)
    assert r_dificil["interval_days"] == round(7 * 0.6)


def test_intervalo_repete_o_maior_apos_o_fim_da_lista(ctx):
    review_id = reviews_service.create_review(discipline_id=1)
    for _ in range(8):
        reviews_service.complete_review(review_id, difficulty="media")
    row = query_one("SELECT interval_days FROM reviews WHERE id = ?", (review_id,))
    assert row["interval_days"] == 60


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
