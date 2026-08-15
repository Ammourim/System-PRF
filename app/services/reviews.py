"""Revisao espacada - fila simples, intervalos configuraveis.

Decisao consciente: nao ha algoritmo sofisticado (FSRS/SM-2) aqui. A lista de
intervalos vem de Configuracoes (`review_intervals`, padrao 1,7,15,30,60) e a
dificuldade informada ao concluir apenas encurta ou alonga o proximo intervalo.
E previsivel, auditavel e o usuario pode sobrescrever qualquer data na mao.
"""

from __future__ import annotations

import sqlite3

from ..db import execute, insert, query_all, query_one, scalar
from ..utils import add_days, today_iso
from . import settings as settings_service

METHODS = {
    "questoes": "Questoes",
    "flashcards": "Flashcards",
    "recuperacao_ativa": "Recuperacao ativa",
    "releitura": "Releitura",
    "caderno_erros": "Caderno de erros",
    "mista": "Revisao mista",
}

DIFFICULTIES = {"facil": "Facil", "media": "Media", "dificil": "Dificil"}


def intervals() -> list[int]:
    values = settings_service.get_list_int("review_intervals")
    return values or [1, 7, 15, 30, 60]


def interval_for_step(step: int) -> int:
    values = intervals()
    if step < len(values):
        return values[step]
    # Depois do ultimo intervalo, repete o maior (nao inventa datas absurdas).
    return values[-1]


def create_review(discipline_id: int, subject_id: int | None = None, title: str = "",
                  origin_date: str | None = None, method: str = "questoes",
                  difficulty: str = "media", notes: str = "",
                  first_interval: int | None = None) -> int:
    origin = origin_date or today_iso()
    interval = first_interval if first_interval is not None else interval_for_step(0)
    return insert(
        "INSERT INTO reviews (discipline_id, subject_id, title, origin_date, next_date, step,"
        " interval_days, difficulty, method, status, notes)"
        " VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'pendente', ?)",
        (discipline_id, subject_id, title, origin, add_days(origin, interval), interval,
         difficulty, method, notes),
    )


def complete_review(review_id: int, difficulty: str | None = None, method: str | None = None,
                    done_date: str | None = None, notes: str | None = None) -> dict:
    """Conclui a revisao e agenda a proxima.

    O intervalo base e o do proximo passo da lista; a dificuldade multiplica:
    facil alonga, dificil encurta, media mantem.
    """
    review = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    if review is None:
        return {}

    done = done_date or today_iso()
    difficulty = difficulty or review["difficulty"]
    method = method or review["method"]
    next_step = int(review["step"]) + 1
    base = interval_for_step(next_step)

    if difficulty == "facil":
        factor = settings_service.get_float("review_difficulty_easy_factor", 1.5)
    elif difficulty == "dificil":
        factor = settings_service.get_float("review_difficulty_hard_factor", 0.6)
    else:
        factor = 1.0
    interval = max(1, int(round(base * factor)))

    execute(
        "UPDATE reviews SET step = ?, interval_days = ?, next_date = ?, difficulty = ?,"
        " method = ?, last_done_at = ?, times_done = times_done + 1, status = 'pendente',"
        " notes = COALESCE(?, notes) WHERE id = ?",
        (next_step, interval, add_days(done, interval), difficulty, method, done, notes,
         review_id),
    )
    return {"next_date": add_days(done, interval), "interval_days": interval, "step": next_step}


def snooze(review_id: int, days: int = 1) -> None:
    review = query_one("SELECT next_date FROM reviews WHERE id = ?", (review_id,))
    if review is None:
        return
    base = max(review["next_date"], today_iso())
    execute("UPDATE reviews SET next_date = ? WHERE id = ?", (add_days(base, days), review_id))


def archive(review_id: int) -> None:
    execute("UPDATE reviews SET status = 'arquivada' WHERE id = ?", (review_id,))


def reactivate(review_id: int) -> None:
    execute(
        "UPDATE reviews SET status = 'pendente', next_date = ? WHERE id = ?",
        (today_iso(), review_id),
    )


def _decorate(rows: list[sqlite3.Row], reference: str) -> list[dict]:
    out = []
    for row in rows:
        data = dict(row)
        if row["next_date"] < reference:
            data["urgency"] = "atrasada"
        elif row["next_date"] == reference:
            data["urgency"] = "hoje"
        else:
            data["urgency"] = "futura"
        out.append(data)
    return out


def due(reference: str | None = None, limit: int | None = None) -> list[dict]:
    """Revisoes vencidas ou de hoje - a fila principal do dashboard."""
    reference = reference or today_iso()
    sql = (
        "SELECT r.*, d.name AS discipline_name, d.short_name, s.name AS subject_name"
        " FROM reviews r JOIN disciplines d ON d.id = r.discipline_id"
        " LEFT JOIN subjects s ON s.id = r.subject_id"
        " WHERE r.status = 'pendente' AND r.next_date <= ?"
        " ORDER BY r.next_date, d.incidence DESC"
    )
    params: tuple = (reference,)
    if limit:
        sql += " LIMIT ?"
        params = (reference, limit)
    return _decorate(query_all(sql, params), reference)


def upcoming(days: int = 7, reference: str | None = None) -> list[dict]:
    reference = reference or today_iso()
    return _decorate(
        query_all(
            "SELECT r.*, d.name AS discipline_name, d.short_name, s.name AS subject_name"
            " FROM reviews r JOIN disciplines d ON d.id = r.discipline_id"
            " LEFT JOIN subjects s ON s.id = r.subject_id"
            " WHERE r.status = 'pendente' AND r.next_date > ? AND r.next_date <= ?"
            " ORDER BY r.next_date",
            (reference, add_days(reference, days)),
        ),
        reference,
    )


def counts(reference: str | None = None) -> dict:
    reference = reference or today_iso()
    return {
        "due": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE status = 'pendente' AND next_date <= ?",
            (reference,), 0)),
        "late": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE status = 'pendente' AND next_date < ?",
            (reference,), 0)),
        "week": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE status = 'pendente' AND next_date <= ?",
            (add_days(reference, 7),), 0)),
        "total": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE status = 'pendente'", (), 0)),
    }
