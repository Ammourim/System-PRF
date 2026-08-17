"""HOJE - a tela inicial e o fluxo diario inteiro.

Ela responde duas perguntas e nada mais:

    "O que eu preciso estudar hoje?"   -> objetivos do dia
    "O que eu preciso revisar hoje?"   -> fila de revisoes

O resto do sistema (simulados, desempenho, TAF, faculdade, ciclo detalhado)
continua existindo, mas fora daqui.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import insert, query_all, query_one
from ..services import reviews as reviews_service
from ..services import subjects as subjects_service
from ..services import today as today_service
from ..utils import (as_bool, as_int, as_opt_int, as_text, date_br, parse_minutes,
                     percentage, today_iso)
from .common import redirect_target

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    today = today_iso()
    return render_template(
        "dashboard/index.html",
        objectives=today_service.objectives(today),
        open_subjects=today_service.open_subjects(limit=8),
        due_reviews=reviews_service.due(today),
        review_counts=reviews_service.counts(today),
        summary=today_service.summary(today),
    )


# --------------------------------------------------------------------------
# Registrar estudo (o formulario curto)
# --------------------------------------------------------------------------
@bp.route("/estudar")
def study_form():
    discipline_id = as_opt_int(request.args.get("discipline_id"))
    discipline = None
    if discipline_id:
        discipline = query_one("SELECT * FROM disciplines WHERE id = ?", (discipline_id,))
    if discipline is None:
        flash("Escolha uma disciplina na tela inicial.", "error")
        return redirect(url_for("dashboard.index"))

    return render_template(
        "dashboard/estudar.html",
        discipline=discipline,
        subject_suggestions=query_all(
            "SELECT id, name, status FROM subjects WHERE discipline_id = ?"
            " ORDER BY (status = 'em_andamento') DESC, name", (discipline_id,)),
        subject_name=as_text(request.args.get("assunto"), max_length=120),
    )


@bp.route("/estudar", methods=["POST"])
def study_save():
    """Grava o estudo. Somente disciplina e assunto importam - o resto e opcional."""
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    if not discipline_id:
        flash("Informe a disciplina.", "error")
        return redirect(url_for("dashboard.index"))

    date = as_text(request.form.get("date"), today_iso())
    subject_id = subjects_service.resolve(
        discipline_id, request.form.get("subject_name"),
        as_opt_int(request.form.get("subject_id")))
    if not subject_id:
        flash("Informe o assunto estudado.", "error")
        return redirect(url_for("dashboard.study_form", discipline_id=discipline_id))
    subjects_service.mark_in_progress(subject_id)

    minutes = max(0, parse_minutes(request.form.get("minutes"), 0))
    notes = as_text(request.form.get("notes"))
    session_id = insert(
        "INSERT INTO study_sessions (date, discipline_id, subject_id, type, planned_minutes,"
        " actual_minutes, notes, completed) VALUES (?, ?, ?, 'teoria', 0, ?, ?, 1)",
        (date, discipline_id, subject_id, minutes, notes))

    messages = ["Estudo registrado."]
    if minutes:
        messages[0] = f"Estudo registrado ({minutes} min)."

    # Questoes: apenas registro, nunca interferem em nada automaticamente.
    total = as_int(request.form.get("questions_total"), 0)
    if total > 0:
        correct = max(0, min(as_int(request.form.get("questions_correct"), 0), total))
        pct = percentage(correct, total)
        insert(
            "INSERT INTO questions (date, discipline_id, subject_id, total, correct, wrong,"
            " percentage, kind, notes, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, 'novo', ?, ?)",
            (date, discipline_id, subject_id, total, correct, total - correct, pct, notes,
             session_id))
        messages.append(f"{total} questoes ({pct:.0f}% de acerto).")

    # O usuario pode declarar o fim do assunto no mesmo formulario.
    if as_bool(request.form.get("finish_subject")):
        return _finish(subject_id, date, schedule=None,
                       extra_messages=messages)

    messages.append("O assunto continua em andamento.")
    flash(" ".join(messages), "success")
    return redirect(url_for("dashboard.index"))


# --------------------------------------------------------------------------
# Concluir assunto -> inicio da revisao espacada
# --------------------------------------------------------------------------
def _finish(subject_id: int, date: str, schedule: bool | None,
            extra_messages: list[str] | None = None) -> "object":
    """Conclui o assunto. `schedule=None` pergunta ao usuario na tela seguinte."""
    subject = subjects_service.complete(subject_id, date)
    if subject is None:
        flash("Assunto nao encontrado.", "error")
        return redirect(url_for("dashboard.index"))

    if schedule is None:
        for message in extra_messages or []:
            flash(message, "success")
        return redirect(url_for("dashboard.finish_subject_form", subject_id=subject_id))

    messages = list(extra_messages or [])
    messages.append(f"Assunto '{subject['name']}' concluido.")
    if schedule:
        created = reviews_service.create_for_subject(
            discipline_id=subject["discipline_id"], subject_id=subject_id,
            title=subject["name"], origin_date=date)
        if created:
            row = query_one("SELECT next_date, interval_days FROM reviews WHERE id = ?",
                            (created,))
            messages.append(
                f"Revisoes agendadas: primeira ({reviews_service.label(row['interval_days'])})"
                f" em {date_br(row['next_date'])}.")
        else:
            messages.append("Ja havia revisao pendente para este assunto - nao dupliquei.")
    else:
        messages.append("Sem revisoes agendadas. Voce pode agendar depois na tela de revisoes.")

    flash(" ".join(messages), "success")
    return redirect(redirect_target(url_for("dashboard.index")))


@bp.route("/assunto/<int:subject_id>/concluir", methods=["POST"])
def finish_subject(subject_id: int):
    """Marca o assunto como concluido e leva a pergunta das revisoes."""
    raw = request.form.get("agendar")
    schedule = None if raw is None else bool(as_bool(raw))
    return _finish(subject_id, as_text(request.form.get("date"), today_iso()), schedule)


@bp.route("/assunto/<int:subject_id>/revisoes")
def finish_subject_form(subject_id: int):
    """A pergunta: "deseja agendar as revisoes espacadas?" - SIM / NAO."""
    subject = query_one(
        "SELECT s.*, d.name AS discipline_name FROM subjects s"
        " JOIN disciplines d ON d.id = s.discipline_id WHERE s.id = ?", (subject_id,))
    if subject is None:
        flash("Assunto nao encontrado.", "error")
        return redirect(url_for("dashboard.index"))
    return render_template(
        "dashboard/agendar.html",
        subject=subject,
        intervals=reviews_service.intervals(),
        pending=reviews_service.pending_for_subject(subject_id),
    )


@bp.route("/assunto/<int:subject_id>/reabrir", methods=["POST"])
def reopen_subject(subject_id: int):
    subjects_service.reopen(subject_id)
    flash("Assunto reaberto - voltou para 'em andamento'.", "success")
    return redirect(redirect_target(url_for("dashboard.index")))
