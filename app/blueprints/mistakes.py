"""Caderno de erros: classificacao, status e conversao em revisao."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all
from ..services import reviews as reviews_service
from ..services import stats
from ..utils import as_bool, as_opt_int, as_text, today_iso
from .common import MISTAKE_CATEGORIES, disciplines, form_subject, redirect_target, subjects

bp = Blueprint("mistakes", __name__, url_prefix="/erros")

STATUSES = {"aberto": "Aberto", "revisado": "Revisado", "consolidado": "Consolidado"}


@bp.route("/")
def index():
    sql = ["SELECT m.*, d.name AS discipline_name, d.short_name, s.name AS subject_name"
           " FROM mistakes m LEFT JOIN disciplines d ON d.id = m.discipline_id"
           " LEFT JOIN subjects s ON s.id = m.subject_id WHERE 1 = 1"]
    params: list = []
    args = request.args
    if as_opt_int(args.get("discipline_id")):
        sql.append(" AND m.discipline_id = ?")
        params.append(as_opt_int(args.get("discipline_id")))
    if args.get("category") in MISTAKE_CATEGORIES:
        sql.append(" AND m.category = ?")
        params.append(args.get("category"))
    if args.get("status") in STATUSES:
        sql.append(" AND m.status = ?")
        params.append(args.get("status"))
    elif not args.get("all"):
        sql.append(" AND m.status != 'consolidado'")
    sql.append(" ORDER BY m.date DESC, m.id DESC LIMIT 400")

    return render_template(
        "mistakes/index.html",
        mistakes=query_all("".join(sql), tuple(params)),
        categories=MISTAKE_CATEGORIES,
        statuses=STATUSES,
        disciplines=disciplines(),
        subjects=subjects(),
        filters=args,
        by_category=stats.mistakes_by_category(days=90),
        review_methods=reviews_service.METHODS,
    )


@bp.route("/salvar", methods=["POST"])
def save():
    mistake_id = as_opt_int(request.form.get("id"))
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    subject_id = form_subject(discipline_id)
    category = request.form.get("category", "C")
    category = category if category in MISTAKE_CATEGORIES else "C"
    status = request.form.get("status", "aberto")
    status = status if status in STATUSES else "aberto"

    values = (as_text(request.form.get("date"), today_iso()), discipline_id, subject_id,
              as_text(request.form.get("question_ref"), max_length=400), category,
              as_text(request.form.get("explanation")), as_text(request.form.get("notes")),
              as_bool(request.form.get("needs_review") or "1"), status)

    if mistake_id:
        execute(
            "UPDATE mistakes SET date = ?, discipline_id = ?, subject_id = ?, question_ref = ?,"
            " category = ?, explanation = ?, notes = ?, needs_review = ?, status = ?"
            " WHERE id = ?", values + (mistake_id,))
        flash("Erro atualizado.", "success")
    else:
        insert(
            "INSERT INTO mistakes (date, discipline_id, subject_id, question_ref, category,"
            " explanation, notes, needs_review, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values)
        flash("Erro registrado no caderno.", "success")
    return redirect(redirect_target(url_for("mistakes.index")))


@bp.route("/<int:mistake_id>/status", methods=["POST"])
def set_status(mistake_id: int):
    status = request.form.get("status", "aberto")
    if status in STATUSES:
        execute("UPDATE mistakes SET status = ? WHERE id = ?", (status, mistake_id))
        flash(f"Erro marcado como {STATUSES[status].lower()}.", "success")
    return redirect(redirect_target(url_for("mistakes.index")))


@bp.route("/<int:mistake_id>/revisar", methods=["POST"])
def to_review(mistake_id: int):
    row = query_all("SELECT * FROM mistakes WHERE id = ?", (mistake_id,))
    if not row:
        flash("Erro nao encontrado.", "error")
        return redirect(url_for("mistakes.index"))
    mistake = row[0]
    if not mistake["discipline_id"]:
        flash("Esse erro nao tem disciplina; edite antes de gerar a revisao.", "error")
        return redirect(url_for("mistakes.index"))
    reviews_service.create_review(
        discipline_id=mistake["discipline_id"], subject_id=mistake["subject_id"],
        title=mistake["question_ref"][:80] or "Revisao do caderno de erros",
        method="caderno_erros", notes=mistake["explanation"])
    execute("UPDATE mistakes SET status = 'revisado' WHERE id = ?", (mistake_id,))
    flash("Revisao criada a partir do erro.", "success")
    return redirect(redirect_target(url_for("mistakes.index")))


@bp.route("/<int:mistake_id>/excluir", methods=["POST"])
def delete(mistake_id: int):
    execute("DELETE FROM mistakes WHERE id = ?", (mistake_id,))
    flash("Erro excluido.", "success")
    return redirect(redirect_target(url_for("mistakes.index")))
