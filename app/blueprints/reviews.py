"""Fila de revisoes: hoje, atrasadas, proximas. Uma linha por assunto."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, query_all
from ..services import reviews as reviews_service
from ..services import subjects as subjects_service
from ..utils import as_int, as_opt_int, as_text, date_br, today_iso
from .common import disciplines, redirect_target

bp = Blueprint("reviews", __name__, url_prefix="/revisoes")


@bp.route("/")
def index():
    return render_template(
        "reviews/index.html",
        due=reviews_service.due(),
        upcoming=reviews_service.upcoming(days=as_int(request.args.get("days"), 30)),
        counts=reviews_service.counts(),
        intervals=reviews_service.intervals(),
        disciplines=disciplines(),
        finished=reviews_service.finished(limit=20),
        archived=query_all(
            "SELECT r.*, d.name AS discipline_name, s.name AS subject_name FROM reviews r"
            " JOIN disciplines d ON d.id = r.discipline_id"
            " LEFT JOIN subjects s ON s.id = r.subject_id"
            " WHERE r.status = 'arquivada' ORDER BY r.next_date DESC LIMIT 20"),
    )


@bp.route("/<int:review_id>")
def detail(review_id: int):
    """Tela da revisao: disciplina, assunto, tipo (D7) e um botao."""
    review = reviews_service.get(review_id)
    if review is None:
        flash("Revisao nao encontrada.", "error")
        return redirect(url_for("reviews.index"))
    return render_template("reviews/revisar.html", review=review,
                           intervals=reviews_service.intervals())


@bp.route("/nova", methods=["POST"])
def create():
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    if not discipline_id:
        flash("Selecione a disciplina da revisao.", "error")
        return redirect(redirect_target(url_for("reviews.index")))
    title = as_text(request.form.get("title"), max_length=120)
    subject_id = subjects_service.resolve(discipline_id, title,
                                          as_opt_int(request.form.get("subject_id")))
    reviews_service.create_review(
        discipline_id=discipline_id,
        subject_id=subject_id,
        title=title,
        origin_date=as_text(request.form.get("origin_date"), today_iso()),
        method=request.form.get("method", "questoes"),
        notes=as_text(request.form.get("notes")),
        first_interval=as_int(request.form.get("first_interval"),
                              reviews_service.interval_for_step(0)),
    )
    flash("Revisao criada.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/concluir", methods=["POST"])
def complete(review_id: int):
    """Conclui a revisao na data REAL e agenda a proxima da sequencia."""
    result = reviews_service.complete_review(
        review_id, done_date=as_text(request.form.get("done_date"), today_iso()))
    if not result:
        flash("Revisao nao encontrada.", "error")
    elif result["finished"]:
        flash("Revisao final concluida. Assunto consolidado - a sequencia terminou.",
              "success")
    else:
        flash(f"Revisao concluida. Proxima ({result['label']}) em"
              f" {date_br(result['next_date'])}.", "success")
    return redirect(redirect_target(url_for("dashboard.index")))


@bp.route("/<int:review_id>/adiar", methods=["POST"])
def snooze(review_id: int):
    days = as_int(request.form.get("days"), 1)
    reviews_service.snooze(review_id, days)
    flash(f"Revisao adiada em {days} dia(s). Nenhuma revisao foi duplicada.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/salvar", methods=["POST"])
def update(review_id: int):
    execute(
        "UPDATE reviews SET title = ?, next_date = ?, interval_days = ?, notes = ? WHERE id = ?",
        (as_text(request.form.get("title"), max_length=120),
         as_text(request.form.get("next_date"), today_iso()),
         max(1, as_int(request.form.get("interval_days"), 1)),
         as_text(request.form.get("notes")), review_id))
    flash("Revisao atualizada.", "success")
    return redirect(redirect_target(url_for("reviews.index")))


@bp.route("/<int:review_id>/arquivar", methods=["POST"])
def archive(review_id: int):
    reviews_service.archive(review_id)
    flash("Revisao arquivada - saiu da fila.", "success")
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
