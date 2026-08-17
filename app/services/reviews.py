"""Revisao espacada - o coracao do sistema.

Regra unica, sem algoritmo: data real de conclusao + proximo intervalo da lista.

  concluiu o assunto  -> D1
  concluiu a D1       -> D7
  concluiu a D7       -> D15
  concluiu a D15      -> D30
  concluiu a D30      -> D60
  concluiu a D60      -> assunto consolidado (a fila termina, nao se repete)

A lista de intervalos vem de Configuracoes (`review_intervals`, padrao
1,7,15,30,60). Revisao atrasada NAO gera revisao duplicada: a mesma linha
continua vencida, e a proxima data e calculada a partir do dia em que voce
realmente fez - nao da data que estava planejada.
"""

from __future__ import annotations

import sqlite3

from ..db import execute, insert, query_all, query_one, scalar
from ..utils import add_days, days_between, today_iso
from . import settings as settings_service
from .cycle import DEFAULT_PRIORITY, PRIORITY_ORDER

METHODS = {
    "questoes": "Questoes",
    "flashcards": "Flashcards",
    "recuperacao_ativa": "Recuperacao ativa",
    "releitura": "Releitura",
    "caderno_erros": "Caderno de erros",
    "mista": "Revisao mista",
}

# Mantido apenas por compatibilidade com dados antigos: a dificuldade nao altera
# mais nenhum intervalo (era o unico calculo "esperto" que restava na fila).
DIFFICULTIES = {"facil": "Facil", "media": "Media", "dificil": "Dificil"}

# Ordena a fila do dia por prioridade da disciplina (mesmo vocabulario do resto).
_PRIORITY_SQL = ("CASE d.priority " +
                 " ".join(f"WHEN '{key}' THEN {rank}" for key, rank in PRIORITY_ORDER.items()) +
                 f" ELSE {PRIORITY_ORDER[DEFAULT_PRIORITY]} END")

_SELECT = (
    "SELECT r.*, d.name AS discipline_name, d.short_name, d.priority,"
    " s.name AS subject_name"
    " FROM reviews r JOIN disciplines d ON d.id = r.discipline_id"
    " LEFT JOIN subjects s ON s.id = r.subject_id"
)


def intervals() -> list[int]:
    values = settings_service.get_list_int("review_intervals")
    return values or [1, 7, 15, 30, 60]


def interval_for_step(step: int) -> int:
    values = intervals()
    if step < len(values):
        return values[step]
    return values[-1]


def total_steps() -> int:
    return len(intervals())


def label(interval_days) -> str:
    """Nome da revisao como o usuario pensa nela: D1, D7, D15..."""
    try:
        return f"D{int(interval_days)}"
    except (TypeError, ValueError):
        return "Revisao"


# --------------------------------------------------------------------------
# Criacao
# --------------------------------------------------------------------------
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


def pending_for_subject(subject_id: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM reviews WHERE subject_id = ? AND status = 'pendente'"
        " ORDER BY next_date LIMIT 1", (subject_id,))


def create_for_subject(discipline_id: int, subject_id: int, title: str = "",
                       origin_date: str | None = None, method: str = "questoes",
                       notes: str = "") -> int | None:
    """Inicia a sequencia de revisoes de um assunto concluido.

    Devolve None quando ja existe revisao pendente para o assunto - concluir o
    mesmo assunto duas vezes nao pode criar duas filas paralelas.
    """
    if subject_id and pending_for_subject(subject_id) is not None:
        return None
    return create_review(discipline_id=discipline_id, subject_id=subject_id, title=title,
                         origin_date=origin_date, method=method, notes=notes)


# --------------------------------------------------------------------------
# Conclusao
# --------------------------------------------------------------------------
def complete_review(review_id: int, difficulty: str | None = None, method: str | None = None,
                    done_date: str | None = None, notes: str | None = None) -> dict:
    """Conclui a revisao e agenda a proxima da sequencia.

    Sem multiplicador, sem dificuldade, sem excecao: proxima data = data real da
    conclusao + proximo intervalo da lista. Depois do ultimo intervalo a revisao
    termina (status 'concluida') e o assunto e considerado consolidado.
    """
    review = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
    if review is None:
        return {}

    done = done_date or today_iso()
    values = intervals()
    next_step = int(review["step"]) + 1

    if next_step >= len(values):
        execute(
            "UPDATE reviews SET step = ?, status = 'concluida', last_done_at = ?,"
            " next_date = ?, times_done = times_done + 1, notes = COALESCE(?, notes)"
            " WHERE id = ?",
            (next_step, done, done, notes, review_id),
        )
        return {
            "finished": True,
            "step": next_step,
            "interval_days": 0,
            "next_date": None,
            "label": label(review["interval_days"]),
        }

    interval = values[next_step]
    next_date = add_days(done, interval)
    execute(
        "UPDATE reviews SET step = ?, interval_days = ?, next_date = ?, method = ?,"
        " last_done_at = ?, times_done = times_done + 1, status = 'pendente',"
        " notes = COALESCE(?, notes) WHERE id = ?",
        (next_step, interval, next_date, method or review["method"], done, notes, review_id),
    )
    return {
        "finished": False,
        "step": next_step,
        "interval_days": interval,
        "next_date": next_date,
        "label": label(interval),
    }


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


# --------------------------------------------------------------------------
# Consultas da fila
# --------------------------------------------------------------------------
def _decorate(rows: list[sqlite3.Row], reference: str) -> list[dict]:
    out = []
    for row in rows:
        data = dict(row)
        data["label"] = label(row["interval_days"])
        data["late_days"] = max(0, days_between(row["next_date"], reference))
        if row["next_date"] < reference:
            data["urgency"] = "atrasada"
        elif row["next_date"] == reference:
            data["urgency"] = "hoje"
        else:
            data["urgency"] = "futura"
        out.append(data)
    return out


def get(review_id: int, reference: str | None = None) -> dict | None:
    reference = reference or today_iso()
    row = query_one(_SELECT + " WHERE r.id = ?", (review_id,))
    if row is None:
        return None
    return _decorate([row], reference)[0]


def due(reference: str | None = None, limit: int | None = None) -> list[dict]:
    """Revisoes vencidas ou de hoje - a fila principal da tela inicial."""
    reference = reference or today_iso()
    sql = (_SELECT + " WHERE r.status = 'pendente' AND r.next_date <= ?"
           f" ORDER BY r.next_date, {_PRIORITY_SQL}, d.name")
    params: tuple = (reference,)
    if limit:
        sql += " LIMIT ?"
        params = (reference, limit)
    return _decorate(query_all(sql, params), reference)


def upcoming(days: int = 7, reference: str | None = None) -> list[dict]:
    reference = reference or today_iso()
    return _decorate(
        query_all(
            _SELECT + " WHERE r.status = 'pendente' AND r.next_date > ? AND r.next_date <= ?"
            " ORDER BY r.next_date",
            (reference, add_days(reference, days)),
        ),
        reference,
    )


def finished(limit: int = 30) -> list[dict]:
    """Assuntos consolidados: percorreram a sequencia inteira."""
    return [dict(r) for r in query_all(
        _SELECT + " WHERE r.status = 'concluida' ORDER BY r.last_done_at DESC LIMIT ?",
        (limit,))]


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
        "consolidated": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE status = 'concluida'", (), 0)),
    }
