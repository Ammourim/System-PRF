"""Faculdade: planejamento independente do ciclo PRF (meta em horas/semana)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, scalar
from ..services import settings as settings_service
from ..utils import as_bool, as_opt_int, as_text, parse_minutes, today_iso
from .common import redirect_target

bp = Blueprint("college", __name__, url_prefix="/faculdade")

TASK_TYPES = {"atividade": "Atividade", "trabalho": "Trabalho", "prova": "Prova",
              "leitura": "Leitura"}


@bp.route("/")
def index():
    today = today_iso()
    week_start = _week_start(today)
    minutes_week = int(scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM college_sessions WHERE date >= ?",
        (week_start,), 0))
    goal_minutes = int(settings_service.get_float("college_hours_per_week", 4) * 60)
    return render_template(
        "college/index.html",
        subjects=query_all(
            "SELECT c.*, COALESCE(s.minutes, 0) AS minutes FROM college_subjects c"
            " LEFT JOIN (SELECT college_subject_id, SUM(minutes) AS minutes"
            "            FROM college_sessions GROUP BY college_subject_id) s"
            " ON s.college_subject_id = c.id WHERE c.active = 1 ORDER BY c.name"),
        tasks=query_all(
            "SELECT t.*, c.name AS subject_name FROM college_tasks t"
            " LEFT JOIN college_subjects c ON c.id = t.college_subject_id"
            " WHERE t.status = 'aberta' ORDER BY t.due_date IS NULL, t.due_date"),
        done_tasks=query_all(
            "SELECT t.*, c.name AS subject_name FROM college_tasks t"
            " LEFT JOIN college_subjects c ON c.id = t.college_subject_id"
            " WHERE t.status = 'concluida' ORDER BY t.due_date DESC LIMIT 15"),
        sessions=query_all(
            "SELECT s.*, c.name AS subject_name FROM college_sessions s"
            " LEFT JOIN college_subjects c ON c.id = s.college_subject_id"
            " ORDER BY s.date DESC LIMIT 30"),
        task_types=TASK_TYPES,
        minutes_week=minutes_week,
        goal_minutes=goal_minutes,
        week_start=week_start,
        today=today,
    )


def _week_start(day: str) -> str:
    from ..utils import add_days, parse_date

    date = parse_date(day)
    return add_days(date, -date.weekday())


@bp.route("/disciplinas", methods=["POST"])
def save_subject():
    subject_id = as_opt_int(request.form.get("id"))
    name = as_text(request.form.get("name"), max_length=120)
    if not name:
        flash("Informe o nome da disciplina.", "error")
        return redirect(url_for("college.index"))
    professor = as_text(request.form.get("professor"), max_length=80)
    notes = as_text(request.form.get("notes"))
    if subject_id:
        execute(
            "UPDATE college_subjects SET name = ?, professor = ?, notes = ?, active = ?"
            " WHERE id = ?",
            (name, professor, notes, as_bool(request.form.get("active") or "1"), subject_id))
        flash("Disciplina da faculdade atualizada.", "success")
    else:
        insert("INSERT INTO college_subjects (name, professor, notes) VALUES (?, ?, ?)",
               (name, professor, notes))
        flash("Disciplina da faculdade cadastrada.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/disciplinas/<int:subject_id>/excluir", methods=["POST"])
def delete_subject(subject_id: int):
    execute("UPDATE college_subjects SET active = 0 WHERE id = ?", (subject_id,))
    flash("Disciplina desativada.", "success")
    return redirect(url_for("college.index"))


@bp.route("/tarefas", methods=["POST"])
def save_task():
    task_id = as_opt_int(request.form.get("id"))
    title = as_text(request.form.get("title"), max_length=160)
    if not title:
        flash("Informe o titulo da atividade.", "error")
        return redirect(url_for("college.index"))
    kind = request.form.get("type", "atividade")
    values = (as_opt_int(request.form.get("college_subject_id")), title,
              kind if kind in TASK_TYPES else "atividade",
              as_text(request.form.get("due_date")) or None,
              as_text(request.form.get("notes")))
    if task_id:
        execute(
            "UPDATE college_tasks SET college_subject_id = ?, title = ?, type = ?,"
            " due_date = ?, notes = ? WHERE id = ?", values + (task_id,))
        flash("Atividade atualizada.", "success")
    else:
        insert(
            "INSERT INTO college_tasks (college_subject_id, title, type, due_date, notes)"
            " VALUES (?, ?, ?, ?, ?)", values)
        flash("Atividade cadastrada.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/tarefas/<int:task_id>/status", methods=["POST"])
def task_status(task_id: int):
    status = "concluida" if request.form.get("status") == "concluida" else "aberta"
    execute("UPDATE college_tasks SET status = ? WHERE id = ?", (status, task_id))
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/tarefas/<int:task_id>/excluir", methods=["POST"])
def delete_task(task_id: int):
    execute("DELETE FROM college_tasks WHERE id = ?", (task_id,))
    flash("Atividade excluida.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/sessoes", methods=["POST"])
def save_session():
    minutes = parse_minutes(request.form.get("minutes"), 0)
    if minutes <= 0:
        flash("Informe o tempo estudado.", "error")
        return redirect(url_for("college.index"))
    insert(
        "INSERT INTO college_sessions (date, college_subject_id, minutes, notes)"
        " VALUES (?, ?, ?, ?)",
        (as_text(request.form.get("date"), today_iso()),
         as_opt_int(request.form.get("college_subject_id")), minutes,
         as_text(request.form.get("notes"))))
    flash(f"{minutes} min de faculdade registrados.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/sessoes/<int:session_id>/excluir", methods=["POST"])
def delete_session(session_id: int):
    execute("DELETE FROM college_sessions WHERE id = ?", (session_id,))
    flash("Registro excluido.", "success")
    return redirect(redirect_target(url_for("college.index")))
