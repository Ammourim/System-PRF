"""Sessoes de estudo - o registro manual, que precisa ser rapido.

Um unico formulario grava a sessao, opcionalmente as questoes daquela sessao,
opcionalmente agenda a revisao e opcionalmente avanca o ciclo.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one
from ..services import cycle as cycle_service
from ..services import reviews as reviews_service
from ..utils import (as_bool, as_int, as_opt_int, as_text, parse_minutes, percentage,
                     today_iso)
from .common import SESSION_TYPES, disciplines, form_subject, redirect_target, subjects

bp = Blueprint("sessions", __name__, url_prefix="/sessoes")


def _list_sessions(limit: int = 200) -> list:
    discipline_id = as_opt_int(request.args.get("discipline_id"))
    kind = request.args.get("type") or ""
    start = request.args.get("start") or ""
    end = request.args.get("end") or ""

    sql = ["SELECT s.*, d.name AS discipline_name, d.short_name, sub.name AS subject_name,"
           " q.total AS q_total, q.correct AS q_correct, q.percentage AS q_pct"
           " FROM study_sessions s"
           " LEFT JOIN disciplines d ON d.id = s.discipline_id"
           " LEFT JOIN subjects sub ON sub.id = s.subject_id"
           " LEFT JOIN questions q ON q.session_id = s.id"
           " WHERE 1 = 1"]
    params: list = []
    if discipline_id:
        sql.append(" AND s.discipline_id = ?")
        params.append(discipline_id)
    if kind:
        sql.append(" AND s.type = ?")
        params.append(kind)
    if start:
        sql.append(" AND s.date >= ?")
        params.append(start)
    if end:
        sql.append(" AND s.date <= ?")
        params.append(end)
    sql.append(" ORDER BY s.date DESC, s.id DESC LIMIT ?")
    params.append(limit)
    return query_all("".join(sql), tuple(params))


@bp.route("/")
def index():
    rows = _list_sessions()
    total_minutes = sum(r["actual_minutes"] or 0 for r in rows)
    total_questions = sum(r["q_total"] or 0 for r in rows)
    total_correct = sum(r["q_correct"] or 0 for r in rows)
    return render_template(
        "sessions/index.html",
        sessions=rows,
        disciplines=disciplines(),
        session_types=SESSION_TYPES,
        totals={
            "minutes": total_minutes,
            "questions": total_questions,
            "accuracy": percentage(total_correct, total_questions) if total_questions else None,
            "count": len(rows),
        },
        filters=request.args,
    )


@bp.route("/nova")
def new():
    block_id = as_opt_int(request.args.get("block_id"))
    block = None
    if block_id:
        block = query_one(
            "SELECT b.*, d.name AS discipline_name FROM cycle_blocks b"
            " JOIN disciplines d ON d.id = b.discipline_id WHERE b.id = ?", (block_id,))
    return render_template(
        "sessions/form.html",
        session=None,
        block=block,
        disciplines=disciplines(),
        subjects=subjects(),
        session_types=SESSION_TYPES,
        review_methods=reviews_service.METHODS,
    )


@bp.route("/salvar", methods=["POST"])
def save():
    session_id = as_opt_int(request.form.get("id"))
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    subject_id = form_subject(discipline_id)
    date = as_text(request.form.get("date"), today_iso())
    kind = request.form.get("type", "teoria")
    if kind not in SESSION_TYPES:
        kind = "outro"
    planned = parse_minutes(request.form.get("planned_minutes"), 0)
    actual = parse_minutes(request.form.get("actual_minutes"), 0)
    notes = as_text(request.form.get("notes"))
    completed = as_bool(request.form.get("completed") or "1")
    block_id = as_opt_int(request.form.get("block_id"))
    cycle = cycle_service.active_cycle()
    cycle_id = as_opt_int(request.form.get("cycle_id")) or (cycle["id"] if cycle else None)

    if actual <= 0 and planned > 0:
        actual = planned
    if actual <= 0:
        flash("Informe o tempo realizado (em minutos) para registrar a sessao.", "error")
        return redirect(request.referrer or url_for("sessions.new"))

    if session_id:
        execute(
            "UPDATE study_sessions SET date = ?, discipline_id = ?, subject_id = ?, type = ?,"
            " planned_minutes = ?, actual_minutes = ?, notes = ?, completed = ? WHERE id = ?",
            (date, discipline_id, subject_id, kind, planned, actual, notes, completed,
             session_id),
        )
    else:
        session_id = insert(
            "INSERT INTO study_sessions (date, discipline_id, subject_id, type, planned_minutes,"
            " actual_minutes, notes, completed, cycle_id, block_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (date, discipline_id, subject_id, kind, planned, actual, notes, completed,
             cycle_id, block_id),
        )

    messages = [f"Sessao registrada: {actual} min."]

    # Questoes informadas junto com a sessao.
    total = as_int(request.form.get("questions_total"), 0)
    correct = as_int(request.form.get("questions_correct"), 0)
    if total > 0:
        correct = max(0, min(correct, total))
        existing = query_one("SELECT id FROM questions WHERE session_id = ?", (session_id,))
        pct = percentage(correct, total)
        q_kind = "revisao" if kind == "revisao" else "novo"
        if existing:
            execute(
                "UPDATE questions SET date = ?, discipline_id = ?, subject_id = ?, total = ?,"
                " correct = ?, wrong = ?, percentage = ?, banca = ?, source = ?, kind = ?,"
                " notes = ? WHERE id = ?",
                (date, discipline_id, subject_id, total, correct, total - correct, pct,
                 as_text(request.form.get("banca")), as_text(request.form.get("source")),
                 q_kind, notes, existing["id"]),
            )
        else:
            insert(
                "INSERT INTO questions (date, discipline_id, subject_id, total, correct, wrong,"
                " percentage, banca, source, kind, notes, session_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, discipline_id, subject_id, total, correct, total - correct, pct,
                 as_text(request.form.get("banca")), as_text(request.form.get("source")),
                 q_kind, notes, session_id),
            )
        messages.append(f"{total} questoes ({pct:.0f}% de acerto).")

    # Revisao opcional.
    if as_bool(request.form.get("create_review")) and discipline_id:
        title = ""
        if subject_id:
            row = query_one("SELECT name FROM subjects WHERE id = ?", (subject_id,))
            title = row["name"] if row else ""
        reviews_service.create_review(
            discipline_id=discipline_id, subject_id=subject_id, title=title, origin_date=date,
            method=request.form.get("review_method", "questoes"))
        messages.append("Revisao agendada.")

    # Avanco do ciclo (sempre explicito).
    if as_bool(request.form.get("advance_cycle")) and cycle_id:
        cycle_service.advance(cycle_id, block_id, mark_done=bool(block_id))
        messages.append("Ciclo avancou para o proximo bloco.")

    flash(" ".join(messages), "success")
    return redirect(redirect_target(url_for("dashboard.index")))


@bp.route("/<int:session_id>/editar")
def edit(session_id: int):
    row = query_one("SELECT * FROM study_sessions WHERE id = ?", (session_id,))
    if row is None:
        flash("Sessao nao encontrada.", "error")
        return redirect(url_for("sessions.index"))
    question = query_one("SELECT * FROM questions WHERE session_id = ?", (session_id,))
    return render_template(
        "sessions/form.html",
        session=row,
        question=question,
        block=None,
        disciplines=disciplines(),
        subjects=subjects(),
        session_types=SESSION_TYPES,
        review_methods=reviews_service.METHODS,
    )


@bp.route("/<int:session_id>/excluir", methods=["POST"])
def delete(session_id: int):
    execute("DELETE FROM questions WHERE session_id = ?", (session_id,))
    execute("DELETE FROM study_sessions WHERE id = ?", (session_id,))
    flash("Sessao excluida.", "success")
    return redirect(redirect_target(url_for("sessions.index")))
