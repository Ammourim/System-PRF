"""Fila de revisoes: hoje, atrasadas, proximas - sem inundar calendario."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all
from ..services import reviews as reviews_service
from ..utils import as_int, as_opt_int, as_text, today_iso
from .common import disciplines, form_subject, redirect_target, subjects

bp = Blueprint("reviews", __name__, url_prefix="/revisoes")


@bp.route("/")
def index():
    return render_template(
        "reviews/index.html",
        due=reviews_service.due(),
        upcoming=reviews_service.upcoming(days=as_int(request.args.get("days"), 14)),
        counts=reviews_service.counts(),
        methods=reviews_service.METHODS,
        difficulties=reviews_service.DIFFICULTIES,
        intervals=reviews_service.intervals(),
        disciplines=disciplines(),
        subjects=subjects(),
        archived=query_all(
            "SELECT r.*, d.name AS discipline_name, s.name AS subject_name FROM reviews r"
            " JOIN disciplines d ON d.id = r.discipline_id"
            " LEFT JOIN subjects s ON s.id = r.subject_id"
            " WHERE r.status = 'arquivada' ORDER BY r.next_date DESC LIMIT 30"),
    )


@bp.route("/nova", methods=["POST"])
def create():
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    if not discipline_id:
        flash("Selecione a disciplina da revisao.", "error")
        return redirect(redirect_target(url_for("reviews.index")))
    subject_id = form_subject(discipline_id)
    reviews_service.create_review(
        discipline_id=discipline_id,
        subject_id=subject_id,
        title=as_text(request.form.get("title"), max_length=120),
        origin_date=as_text(request.form.get("origin_date"), today_iso()),
        method=request.form.get("method", "questoes"),
        difficulty=request.form.get("difficulty", "media"),
        notes=as_text(request.form.get("notes")),
        first_interval=as_int(request.form.get("first_interval"),
                              reviews_service.interval_for_step(0)),
    )
    flash("Revisao criada.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/concluir", methods=["POST"])
def complete(review_id: int):
    result = reviews_service.complete_review(
        review_id,
        difficulty=request.form.get("difficulty"),
        method=request.form.get("method"),
        done_date=as_text(request.form.get("done_date"), today_iso()),
    )
    if result:
        flash(f"Revisao concluida. Proxima em {result['interval_days']} dia(s).", "success")
        if request.form.get("register_session"):
            row = query_all(
                "SELECT discipline_id, subject_id FROM reviews WHERE id = ?", (review_id,))
            minutes = as_int(request.form.get("minutes"), 0)
            if row and minutes > 0:
                insert(
                    "INSERT INTO study_sessions (date, discipline_id, subject_id, type,"
                    " planned_minutes, actual_minutes, notes, completed)"
                    " VALUES (?, ?, ?, 'revisao', ?, ?, 'Revisao concluida pela fila', 1)",
                    (today_iso(), row[0]["discipline_id"], row[0]["subject_id"], minutes,
                     minutes))
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/adiar", methods=["POST"])
def snooze(review_id: int):
    days = as_int(request.form.get("days"), 1)
    reviews_service.snooze(review_id, days)
    flash(f"Revisao adiada em {days} dia(s).", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/salvar", methods=["POST"])
def update(review_id: int):
    execute(
        "UPDATE reviews SET title = ?, next_date = ?, interval_days = ?, difficulty = ?,"
        " method = ?, notes = ? WHERE id = ?",
        (as_text(request.form.get("title"), max_length=120),
         as_text(request.form.get("next_date"), today_iso()),
         max(1, as_int(request.form.get("interval_days"), 1)),
         request.form.get("difficulty", "media"),
         request.form.get("method", "questoes"),
         as_text(request.form.get("notes")), review_id))
    flash("Revisao atualizada.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/arquivar", methods=["POST"])
def archive(review_id: int):
    reviews_service.archive(review_id)
    flash("Revisao arquivada (assunto consolidado).", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/reativar", methods=["POST"])
def reactivate(review_id: int):
    reviews_service.reactivate(review_id)
    flash("Revisao reativada para hoje.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/excluir", methods=["POST"])
def delete(review_id: int):
    execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    flash("Revisao excluida.", "success")
    return redirect(redirect_target(url_for("reviews.index")))
