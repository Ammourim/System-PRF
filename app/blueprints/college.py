"""Faculdade: planejamento independente do ciclo PRF.

Duas telas em uma so pagina, na ordem em que sao usadas:

  1. O QUE ESTUDAR - o plano ate o prazo (`services/college.plan`), com o tema
     da vez em destaque. Concluir o tema abre a revisao espacada dele.
  2. O QUE REVISAR - a fila de revisao da faculdade, independente da fila do PRF.

Prazos de atividade (`college_tasks`) e tempo estudado (`college_sessions`)
continuam existindo como estavam.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, scalar
from ..services import college as college_service
from ..services import settings as settings_service
from ..utils import as_bool, as_int, as_opt_int, as_text, parse_minutes, today_iso
from .common import redirect_target

bp = Blueprint("college", __name__, url_prefix="/faculdade")

TASK_TYPES = {"atividade": "Atividade", "trabalho": "Trabalho", "prova": "Prova",
              "leitura": "Leitura"}

PLAN_PREVIEW = 12   # quantos temas do plano aparecem sem abrir o plano inteiro


@bp.route("/")
def index():
    today = today_iso()
    week_start = _week_start(today)
    minutes_week = int(scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM college_sessions WHERE date >= ?",
        (week_start,), 0))
    goal_minutes = int(settings_service.get_float("college_hours_per_week", 4) * 60)
    # `plan()` regrava as datas a cada visita: o plano se conserta sozinho
    # quando voce atrasa ou adianta um tema.
    plan = college_service.plan(today)
    return render_template(
        "college/index.html",
        plan=plan,
        plan_preview=PLAN_PREVIEW,
        current_topic=plan[0] if plan else None,
        progress=college_service.progress(today),
        topics=college_service.topics(),
        reviews_due=college_service.due(today),
        reviews_upcoming=college_service.upcoming(days=14, reference=today),
        review_counts=college_service.review_counts(today),
        review_intervals=college_service.intervals(),
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
            "SELECT s.*, c.name AS subject_name, t.name AS topic_name"
            " FROM college_sessions s"
            " LEFT JOIN college_subjects c ON c.id = s.college_subject_id"
            " LEFT JOIN college_topics t ON t.id = s.college_topic_id"
            " ORDER BY s.date DESC, s.id DESC LIMIT 30"),
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


# --------------------------------------------------------------------------
# Temas: o conteudo que precisa caber ate o prazo
# --------------------------------------------------------------------------
@bp.route("/temas", methods=["POST"])
def save_topic():
    subject_id = as_opt_int(request.form.get("college_subject_id"))
    name = as_text(request.form.get("name"), max_length=160)
    if not subject_id or not name:
        flash("Informe a disciplina e o nome do tema.", "error")
        return redirect(redirect_target(url_for("college.index")))
    if college_service.add_topic(subject_id, name) is None:
        flash("Esse tema ja existe nesta disciplina.", "error")
    else:
        college_service.plan()
        flash("Tema cadastrado e encaixado no plano.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/temas/<int:topic_id>/concluir", methods=["POST"])
def complete_topic(topic_id: int):
    """Conclui o tema: abre a revisao espacada e redistribui o que sobrou."""
    result = college_service.complete_topic(
        topic_id,
        done_date=as_text(request.form.get("done_date"), today_iso()),
        minutes=parse_minutes(request.form.get("minutes"), 0),
        notes=as_text(request.form.get("notes")),
    )
    if not result:
        flash("Tema nao encontrado ou ja concluido.", "error")
    else:
        primeiro = college_service.interval_for_step(0)
        flash(f"Tema concluido. Primeira revisao (D{primeiro}) agendada.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/temas/<int:topic_id>/hoje", methods=["POST"])
def focus_topic(topic_id: int):
    """Escolhe o tema de hoje - vale so para hoje, depois o plano volta a mandar."""
    topic = college_service.get_topic(topic_id)
    if topic is None or topic["status"] == "concluido":
        flash("Tema nao encontrado ou ja concluido.", "error")
    else:
        college_service.set_focus(topic_id)
        flash(f"Hoje voce estuda: {topic['name']}.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/temas/<int:topic_id>/reabrir", methods=["POST"])
def reopen_topic(topic_id: int):
    college_service.reopen_topic(topic_id)
    flash("Tema reaberto - voltou para o plano e a revisao dele foi arquivada.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/temas/<int:topic_id>/excluir", methods=["POST"])
def delete_topic(topic_id: int):
    college_service.delete_topic(topic_id)
    flash("Tema excluido.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/plano/recalcular", methods=["POST"])
def replan():
    itens = college_service.plan()
    flash(f"Plano refeito: {len(itens)} temas ate {college_service.deadline()}.", "success")
    return redirect(redirect_target(url_for("college.index")))


# --------------------------------------------------------------------------
# Revisao espacada da faculdade
# --------------------------------------------------------------------------
@bp.route("/revisoes/<int:review_id>/concluir", methods=["POST"])
def complete_review(review_id: int):
    result = college_service.complete_review(
        review_id, done_date=as_text(request.form.get("done_date"), today_iso()))
    if not result:
        flash("Revisao nao encontrada.", "error")
    elif result.get("finished"):
        flash("Sequencia completa - tema consolidado.", "success")
    else:
        flash(f"Revisao concluida. Proxima {result['label']} em "
              f"{result['next_date']}.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/revisoes/<int:review_id>/adiar", methods=["POST"])
def snooze_review(review_id: int):
    college_service.snooze_review(review_id, days=as_int(request.form.get("days"), 1))
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/revisoes/<int:review_id>/arquivar", methods=["POST"])
def archive_review(review_id: int):
    college_service.archive_review(review_id)
    flash("Revisao arquivada.", "success")
    return redirect(redirect_target(url_for("college.index")))


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
    topic_id = as_opt_int(request.form.get("college_topic_id"))
    subject_id = as_opt_int(request.form.get("college_subject_id"))
    if topic_id and not subject_id:
        topic = college_service.get_topic(topic_id)
        subject_id = topic["college_subject_id"] if topic else None
    insert(
        "INSERT INTO college_sessions (date, college_subject_id, college_topic_id,"
        " minutes, notes) VALUES (?, ?, ?, ?, ?)",
        (as_text(request.form.get("date"), today_iso()), subject_id, topic_id, minutes,
         as_text(request.form.get("notes"))))
    flash(f"{minutes} min de faculdade registrados.", "success")
    return redirect(redirect_target(url_for("college.index")))


@bp.route("/sessoes/<int:session_id>/excluir", methods=["POST"])
def delete_session(session_id: int):
    execute("DELETE FROM college_sessions WHERE id = ?", (session_id,))
    flash("Registro excluido.", "success")
    return redirect(redirect_target(url_for("college.index")))
