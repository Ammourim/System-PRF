"""Modulo de questoes: registro avulso, filtros e metas."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one
from ..services import cycle as cycle_service
from ..services import settings as settings_service
from ..utils import as_float, as_int, as_opt_int, as_text, percentage, today_iso
from .common import disciplines, form_subject, redirect_target, subjects

bp = Blueprint("questions", __name__, url_prefix="/questoes")


def _filtered() -> list:
    sql = ["SELECT q.*, d.name AS discipline_name, d.short_name, s.name AS subject_name"
           " FROM questions q"
           " LEFT JOIN disciplines d ON d.id = q.discipline_id"
           " LEFT JOIN subjects s ON s.id = q.subject_id WHERE 1 = 1"]
    params: list = []
    args = request.args

    if as_opt_int(args.get("discipline_id")):
        sql.append(" AND q.discipline_id = ?")
        params.append(as_opt_int(args.get("discipline_id")))
    if as_opt_int(args.get("subject_id")):
        sql.append(" AND q.subject_id = ?")
        params.append(as_opt_int(args.get("subject_id")))
    if args.get("banca"):
        sql.append(" AND lower(q.banca) LIKE lower(?)")
        params.append(f"%{args.get('banca')}%")
    if args.get("start"):
        sql.append(" AND q.date >= ?")
        params.append(args.get("start"))
    if args.get("end"):
        sql.append(" AND q.date <= ?")
        params.append(args.get("end"))
    if args.get("max_pct"):
        sql.append(" AND q.percentage <= ?")
        params.append(as_float(args.get("max_pct"), 100))
    if args.get("min_pct"):
        sql.append(" AND q.percentage >= ?")
        params.append(as_float(args.get("min_pct"), 0))
    if args.get("kind") in {"novo", "revisao"}:
        sql.append(" AND q.kind = ?")
        params.append(args.get("kind"))
    if args.get("only_wrong"):
        sql.append(" AND q.wrong > 0")

    sql.append(" ORDER BY q.date DESC, q.id DESC LIMIT 500")
    return query_all("".join(sql), tuple(params))


@bp.route("/")
def index():
    rows = _filtered()
    total = sum(r["total"] for r in rows)
    correct = sum(r["correct"] for r in rows)

    progress = cycle_service.progress()
    goal_folga = settings_service.get_int("questions_goal_per_folga", 50)
    days = {r["date"] for r in rows}

    return render_template(
        "questions/index.html",
        questions=rows,
        disciplines=disciplines(),
        subjects=subjects(),
        filters=request.args,
        totals={
            "total": total,
            "correct": correct,
            "wrong": total - correct,
            "accuracy": percentage(correct, total) if total else None,
            "days": len(days),
            "per_day": round(total / len(days), 1) if days else 0,
        },
        cycle_progress=progress,
        goal_folga=goal_folga,
        folgas=settings_service.get_int("folgas_per_cycle", 7),
        split={
            "new": settings_service.get_int("questions_split_new", 30),
            "review": settings_service.get_int("questions_split_review", 20),
        },
    )


@bp.route("/salvar", methods=["POST"])
def save():
    question_id = as_opt_int(request.form.get("id"))
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    subject_id = form_subject(discipline_id)
    total = as_int(request.form.get("total"), 0)
    correct = as_int(request.form.get("correct"), 0)

    if total <= 0:
        flash("Informe a quantidade de questoes.", "error")
        return redirect(redirect_target(url_for("questions.index")))
    correct = max(0, min(correct, total))
    pct = percentage(correct, total)
    kind = request.form.get("kind", "novo")
    kind = kind if kind in {"novo", "revisao"} else "novo"

    values = (as_text(request.form.get("date"), today_iso()), discipline_id, subject_id,
              total, correct, total - correct, pct, as_text(request.form.get("banca"), max_length=60),
              as_text(request.form.get("source"), max_length=120), kind,
              as_text(request.form.get("notes")))

    if question_id:
        execute(
            "UPDATE questions SET date = ?, discipline_id = ?, subject_id = ?, total = ?,"
            " correct = ?, wrong = ?, percentage = ?, banca = ?, source = ?, kind = ?,"
            " notes = ? WHERE id = ?", values + (question_id,))
        flash("Registro de questoes atualizado.", "success")
    else:
        insert(
            "INSERT INTO questions (date, discipline_id, subject_id, total, correct, wrong,"
            " percentage, banca, source, kind, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values)
        flash(f"{total} questoes registradas ({pct:.0f}% de acerto).", "success")
    return redirect(redirect_target(url_for("questions.index")))


@bp.route("/<int:question_id>/excluir", methods=["POST"])
def delete(question_id: int):
    execute("DELETE FROM questions WHERE id = ?", (question_id,))
    flash("Registro excluido.", "success")
    return redirect(redirect_target(url_for("questions.index")))


@bp.route("/<int:question_id>")
def detail(question_id: int):
    row = query_one(
        "SELECT q.*, d.name AS discipline_name, s.name AS subject_name FROM questions q"
        " LEFT JOIN disciplines d ON d.id = q.discipline_id"
        " LEFT JOIN subjects s ON s.id = q.subject_id WHERE q.id = ?", (question_id,))
    if row is None:
        flash("Registro nao encontrado.", "error")
        return redirect(url_for("questions.index"))
    return render_template("questions/detail.html", question=row,
                           disciplines=disciplines(), subjects=subjects())
