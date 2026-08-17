"""Calculos de desempenho: geral, por disciplina, por assunto e evolucao."""

from __future__ import annotations

from ..db import query_all, query_one, scalar
from ..utils import add_days, percentage, today_iso
from . import settings as settings_service


def _period(days: int | None, reference: str | None = None) -> tuple[str, str]:
    reference = reference or today_iso()
    if not days:
        return ("0001-01-01", reference)
    return (add_days(reference, -days + 1), reference)


def overall(days: int | None = None, reference: str | None = None) -> dict:
    start, end = _period(days, reference)
    minutes = int(scalar(
        "SELECT COALESCE(SUM(actual_minutes), 0) FROM study_sessions"
        " WHERE date BETWEEN ? AND ?", (start, end), 0))
    sessions = int(scalar(
        "SELECT COUNT(*) FROM study_sessions WHERE date BETWEEN ? AND ?", (start, end), 0))
    row = query_one(
        "SELECT COALESCE(SUM(total), 0) AS total, COALESCE(SUM(correct), 0) AS correct"
        " FROM questions WHERE date BETWEEN ? AND ?", (start, end))
    total_q = int(row["total"] or 0)
    correct_q = int(row["correct"] or 0)
    mocks = int(scalar(
        "SELECT COUNT(*) FROM mock_exams WHERE date BETWEEN ? AND ?", (start, end), 0))
    return {
        "start": start,
        "end": end,
        "minutes": minutes,
        "sessions": sessions,
        "questions": total_q,
        "correct": correct_q,
        "wrong": total_q - correct_q,
        "accuracy": percentage(correct_q, total_q) if total_q else None,
        "mocks": mocks,
    }


def by_discipline(days: int | None = None, reference: str | None = None,
                  active_only: bool = True) -> list[dict]:
    start, end = _period(days, reference)
    rows = query_all(
        """
        SELECT d.id, d.name, d.short_name, d.incidence, d.priority, d.status,
               d.target_minutes, d.block_minutes, d.desired_blocks, d.min_blocks,
               d.frequency, d.active,
               COALESCE(q.total, 0)   AS questions,
               COALESCE(q.correct, 0) AS correct,
               COALESCE(s.minutes, 0) AS minutes,
               s.last_date            AS last_studied
        FROM disciplines d
        LEFT JOIN (
            SELECT discipline_id, SUM(total) AS total, SUM(correct) AS correct
            FROM questions WHERE date BETWEEN ? AND ? GROUP BY discipline_id
        ) q ON q.discipline_id = d.id
        LEFT JOIN (
            SELECT discipline_id, SUM(actual_minutes) AS minutes, MAX(date) AS last_date
            FROM study_sessions WHERE date BETWEEN ? AND ? GROUP BY discipline_id
        ) s ON s.discipline_id = d.id
        WHERE (d.active = 1 OR ? = 0)
        ORDER BY CASE d.priority WHEN 'maxima' THEN 0 WHEN 'alta' THEN 1
                                 WHEN 'media' THEN 2 WHEN 'baixa' THEN 3 ELSE 1 END,
                 d.incidence DESC, d.name
        """,
        (start, end, start, end, 1 if active_only else 0),
    )
    out = []
    for row in rows:
        data = dict(row)
        data["accuracy"] = percentage(row["correct"], row["questions"]) if row["questions"] else None
        out.append(data)
    return out


def by_subject(days: int | None = None, min_questions: int = 1,
               reference: str | None = None, limit: int | None = None) -> list[dict]:
    start, end = _period(days, reference)
    sql = """
        SELECT s.id, s.name AS subject_name, d.name AS discipline_name, d.short_name,
               SUM(q.total) AS questions, SUM(q.correct) AS correct, MAX(q.date) AS last_date
        FROM questions q
        JOIN subjects s ON s.id = q.subject_id
        JOIN disciplines d ON d.id = s.discipline_id
        WHERE q.date BETWEEN ? AND ?
        GROUP BY s.id
        HAVING SUM(q.total) >= ?
        ORDER BY (CAST(SUM(q.correct) AS REAL) / SUM(q.total)) ASC
    """
    params: tuple = (start, end, min_questions)
    if limit:
        sql += " LIMIT ?"
        params = (start, end, min_questions, limit)
    return [
        dict(row, accuracy=percentage(row["correct"], row["questions"]))
        for row in query_all(sql, params)
    ]


def weak_points(days: int | None = 90, limit: int = 8, min_questions: int = 10) -> list[dict]:
    """Assuntos com pior aproveitamento (abaixo do limiar configurado)."""
    threshold = settings_service.get_float("performance_mid", 70)
    rows = by_subject(days=days, min_questions=min_questions, limit=None)
    weak = [r for r in rows if r["accuracy"] is not None and r["accuracy"] < threshold]
    return weak[:limit]


def weak_disciplines(days: int | None = 90, limit: int = 5,
                     min_questions: int = 10) -> list[dict]:
    threshold = settings_service.get_float("performance_mid", 70)
    rows = [
        r for r in by_discipline(days=days)
        if r["questions"] >= min_questions and r["accuracy"] is not None
        and r["accuracy"] < threshold
    ]
    rows.sort(key=lambda r: r["accuracy"])
    return rows[:limit]


def evolution(days: int = 30, reference: str | None = None) -> dict:
    """Compara o periodo atual com o periodo imediatamente anterior."""
    reference = reference or today_iso()
    current = overall(days=days, reference=reference)
    previous_ref = add_days(reference, -days)
    previous = overall(days=days, reference=previous_ref)
    delta = None
    if current["accuracy"] is not None and previous["accuracy"] is not None:
        delta = round(current["accuracy"] - previous["accuracy"], 1)
    return {
        "current": current,
        "previous": previous,
        "accuracy_delta": delta,
        "minutes_delta": current["minutes"] - previous["minutes"],
        "questions_delta": current["questions"] - previous["questions"],
        "days": days,
    }


def discipline_evolution(days: int = 30, reference: str | None = None) -> list[dict]:
    """Variacao de acerto por disciplina entre o periodo atual e o anterior."""
    reference = reference or today_iso()
    current = {r["id"]: r for r in by_discipline(days=days, reference=reference)}
    previous = {r["id"]: r for r in by_discipline(days=days, reference=add_days(reference, -days))}
    out = []
    for did, row in current.items():
        prev = previous.get(did)
        delta = None
        if (row["accuracy"] is not None and prev and prev["accuracy"] is not None
                and row["questions"] >= 5 and prev["questions"] >= 5):
            delta = round(row["accuracy"] - prev["accuracy"], 1)
        out.append({
            "id": did,
            "name": row["name"],
            "short_name": row["short_name"],
            "accuracy": row["accuracy"],
            "previous_accuracy": prev["accuracy"] if prev else None,
            "delta": delta,
            "questions": row["questions"],
        })
    out.sort(key=lambda r: (r["delta"] is None, -(r["delta"] or 0)))
    return out


def daily_series(days: int = 30, reference: str | None = None) -> list[dict]:
    """Serie diaria de minutos e questoes (usada nos graficos leves em SVG)."""
    start, end = _period(days, reference)
    minutes = {
        r["date"]: int(r["minutes"] or 0)
        for r in query_all(
            "SELECT date, SUM(actual_minutes) AS minutes FROM study_sessions"
            " WHERE date BETWEEN ? AND ? GROUP BY date", (start, end))
    }
    questions = {
        r["date"]: (int(r["total"] or 0), int(r["correct"] or 0))
        for r in query_all(
            "SELECT date, SUM(total) AS total, SUM(correct) AS correct FROM questions"
            " WHERE date BETWEEN ? AND ? GROUP BY date", (start, end))
    }
    series = []
    for i in range(days):
        day = add_days(start, i)
        total, correct = questions.get(day, (0, 0))
        series.append({
            "date": day,
            "minutes": minutes.get(day, 0),
            "questions": total,
            "accuracy": percentage(correct, total) if total else None,
        })
    return series


def today_summary(reference: str | None = None) -> dict:
    day = reference or today_iso()
    prf_minutes = int(scalar(
        "SELECT COALESCE(SUM(actual_minutes), 0) FROM study_sessions WHERE date = ?", (day,), 0))
    college_minutes = int(scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM college_sessions WHERE date = ?", (day,), 0))
    row = query_one(
        "SELECT COALESCE(SUM(total), 0) AS total, COALESCE(SUM(correct), 0) AS correct"
        " FROM questions WHERE date = ?", (day,))
    # Treino de hoje: a execucao do dia, se houver.
    workout = query_one(
        "SELECT * FROM taf_workout_sessions WHERE date = ?"
        " ORDER BY CASE status WHEN 'em_andamento' THEN 0 ELSE 1 END, id DESC LIMIT 1",
        (day,))
    total_q = int(row["total"] or 0)
    return {
        "date": day,
        "prf_minutes": prf_minutes,
        "college_minutes": college_minutes,
        "questions": total_q,
        "correct": int(row["correct"] or 0),
        "accuracy": percentage(int(row["correct"] or 0), total_q) if total_q else None,
        "questions_goal": settings_service.get_int("questions_goal_per_folga", 50),
        "workout": workout,
    }


def mistakes_by_category(days: int | None = None) -> list[dict]:
    start, end = _period(days)
    rows = query_all(
        "SELECT category, COUNT(*) AS total FROM mistakes"
        " WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC", (start, end))
    return [dict(r) for r in rows]
