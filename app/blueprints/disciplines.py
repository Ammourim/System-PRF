"""Disciplinas e assuntos: pesos, prioridade, status e metas por ciclo."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one, scalar
from ..services import stats
from ..utils import as_bool, as_float, as_int, as_opt_int, as_text, parse_minutes, percentage
from .common import DISCIPLINE_STATUS, PRIORITIES, redirect_target

bp = Blueprint("disciplines", __name__, url_prefix="/disciplinas")


@bp.route("/")
def index():
    rows = stats.by_discipline(days=None)
    total_target = sum(r["target_minutes"] or 0 for r in rows)
    incidence_total = sum(r["incidence"] or 0 for r in rows)
    return render_template(
        "disciplines/index.html",
        disciplines=rows,
        total_target=total_target,
        incidence_total=incidence_total,
        statuses=DISCIPLINE_STATUS,
        priorities=PRIORITIES,
    )


@bp.route("/nova", methods=["POST"])
def create():
    name = as_text(request.form.get("name"), max_length=120)
    if not name:
        flash("Informe o nome da disciplina.", "error")
        return redirect(url_for("disciplines.index"))
    if query_one("SELECT id FROM disciplines WHERE lower(name) = lower(?)", (name,)):
        flash("Ja existe uma disciplina com esse nome.", "error")
        return redirect(url_for("disciplines.index"))
    position = int(scalar("SELECT COALESCE(MAX(position), 0) FROM disciplines", (), 0)) + 1
    insert(
        "INSERT INTO disciplines (name, short_name, incidence, priority, status, block_minutes,"
        " target_minutes, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, as_text(request.form.get("short_name"), name[:20], max_length=30),
         as_float(request.form.get("incidence"), 0),
         request.form.get("priority", "base") if request.form.get("priority") in PRIORITIES
         else "base",
         request.form.get("status", "nao_iniciada")
         if request.form.get("status") in DISCIPLINE_STATUS else "nao_iniciada",
         max(5, parse_minutes(request.form.get("block_minutes"), 60)),
         parse_minutes(request.form.get("target_minutes"), 0), position))
    flash(f"Disciplina '{name}' criada.", "success")
    return redirect(url_for("disciplines.index"))


@bp.route("/<int:discipline_id>")
def detail(discipline_id: int):
    row = query_one("SELECT * FROM disciplines WHERE id = ?", (discipline_id,))
    if row is None:
        flash("Disciplina nao encontrada.", "error")
        return redirect(url_for("disciplines.index"))

    subject_rows = query_all(
        """
        SELECT s.*,
               COALESCE(q.total, 0) AS questions, COALESCE(q.correct, 0) AS correct,
               COALESCE(m.minutes, 0) AS minutes, m.last_date,
               COALESCE(r.pending, 0) AS pending_reviews
        FROM subjects s
        LEFT JOIN (SELECT subject_id, SUM(total) AS total, SUM(correct) AS correct
                   FROM questions GROUP BY subject_id) q ON q.subject_id = s.id
        LEFT JOIN (SELECT subject_id, SUM(actual_minutes) AS minutes, MAX(date) AS last_date
                   FROM study_sessions GROUP BY subject_id) m ON m.subject_id = s.id
        LEFT JOIN (SELECT subject_id, COUNT(*) AS pending FROM reviews
                   WHERE status = 'pendente' GROUP BY subject_id) r ON r.subject_id = s.id
        WHERE s.discipline_id = ? ORDER BY s.name
        """,
        (discipline_id,))
    subject_data = [
        dict(s, accuracy=percentage(s["correct"], s["questions"]) if s["questions"] else None)
        for s in subject_rows
    ]
    return render_template(
        "disciplines/detail.html",
        discipline=row,
        subjects=subject_data,
        statuses=DISCIPLINE_STATUS,
        priorities=PRIORITIES,
        recent_sessions=query_all(
            "SELECT s.*, sub.name AS subject_name FROM study_sessions s"
            " LEFT JOIN subjects sub ON sub.id = s.subject_id"
            " WHERE s.discipline_id = ? ORDER BY s.date DESC LIMIT 10", (discipline_id,)),
        mistakes=query_all(
            "SELECT m.*, sub.name AS subject_name FROM mistakes m"
            " LEFT JOIN subjects sub ON sub.id = m.subject_id"
            " WHERE m.discipline_id = ? AND m.status != 'consolidado'"
            " ORDER BY m.date DESC LIMIT 10", (discipline_id,)),
    )


@bp.route("/<int:discipline_id>/salvar", methods=["POST"])
def update(discipline_id: int):
    priority = request.form.get("priority", "base")
    status = request.form.get("status", "nao_iniciada")
    execute(
        "UPDATE disciplines SET name = ?, short_name = ?, incidence = ?, priority = ?,"
        " status = ?, block_minutes = ?, target_minutes = ?, active = ?, notes = ?"
        " WHERE id = ?",
        (as_text(request.form.get("name"), max_length=120),
         as_text(request.form.get("short_name"), max_length=30),
         as_float(request.form.get("incidence"), 0),
         priority if priority in PRIORITIES else "base",
         status if status in DISCIPLINE_STATUS else "nao_iniciada",
         max(5, parse_minutes(request.form.get("block_minutes"), 60)),
         parse_minutes(request.form.get("target_minutes"), 0),
         as_bool(request.form.get("active")),
         as_text(request.form.get("notes")), discipline_id))
    flash("Disciplina atualizada.", "success")
    return redirect(redirect_target(url_for("disciplines.detail",
                                            discipline_id=discipline_id)))


@bp.route("/pesos", methods=["POST"])
def bulk_update():
    """Edicao rapida de incidencia/meta direto na listagem (ex.: novo edital)."""
    for row in query_all("SELECT id FROM disciplines"):
        did = row["id"]
        if f"incidence_{did}" in request.form:
            execute("UPDATE disciplines SET incidence = ? WHERE id = ?",
                    (as_float(request.form.get(f"incidence_{did}"), 0), did))
        if f"target_{did}" in request.form:
            execute("UPDATE disciplines SET target_minutes = ? WHERE id = ?",
                    (parse_minutes(request.form.get(f"target_{did}"), 0), did))
        if f"priority_{did}" in request.form:
            value = request.form.get(f"priority_{did}")
            if value in PRIORITIES:
                execute("UPDATE disciplines SET priority = ? WHERE id = ?", (value, did))
        if f"status_{did}" in request.form:
            value = request.form.get(f"status_{did}")
            if value in DISCIPLINE_STATUS:
                execute("UPDATE disciplines SET status = ? WHERE id = ?", (value, did))
    flash("Pesos e metas atualizados.", "success")
    return redirect(url_for("disciplines.index"))


@bp.route("/<int:discipline_id>/excluir", methods=["POST"])
def delete(discipline_id: int):
    used = int(scalar("SELECT COUNT(*) FROM study_sessions WHERE discipline_id = ?",
                      (discipline_id,), 0))
    if used:
        execute("UPDATE disciplines SET active = 0 WHERE id = ?", (discipline_id,))
        flash("Disciplina possui historico: foi desativada em vez de excluida.", "success")
    else:
        execute("DELETE FROM disciplines WHERE id = ?", (discipline_id,))
        flash("Disciplina excluida.", "success")
    return redirect(url_for("disciplines.index"))


# --------------------------------------------------------------------------
# Assuntos
# --------------------------------------------------------------------------
@bp.route("/<int:discipline_id>/assuntos", methods=["POST"])
def create_subject(discipline_id: int):
    raw = as_text(request.form.get("name"), max_length=2000)
    if not raw:
        flash("Informe o nome do assunto.", "error")
        return redirect(url_for("disciplines.detail", discipline_id=discipline_id))
    created = 0
    # Aceita varios assuntos de uma vez (um por linha) - cadastro de edital e rapido.
    for line in raw.splitlines():
        name = line.strip()[:120]
        if not name:
            continue
        if query_one("SELECT id FROM subjects WHERE discipline_id = ? AND lower(name) = lower(?)",
                     (discipline_id, name)):
            continue
        insert("INSERT INTO subjects (discipline_id, name, status) VALUES (?, ?, ?)",
               (discipline_id, name, request.form.get("status", "nao_iniciada")))
        created += 1
    flash(f"{created} assunto(s) cadastrado(s).", "success")
    return redirect(url_for("disciplines.detail", discipline_id=discipline_id))


@bp.route("/assuntos/<int:subject_id>/salvar", methods=["POST"])
def update_subject(subject_id: int):
    row = query_one("SELECT discipline_id FROM subjects WHERE id = ?", (subject_id,))
    if row is None:
        flash("Assunto nao encontrado.", "error")
        return redirect(url_for("disciplines.index"))
    execute("UPDATE subjects SET name = ?, status = ?, notes = ? WHERE id = ?",
            (as_text(request.form.get("name"), max_length=120),
             request.form.get("status", "nao_iniciada"),
             as_text(request.form.get("notes")), subject_id))
    flash("Assunto atualizado.", "success")
    return redirect(url_for("disciplines.detail", discipline_id=row["discipline_id"]))


@bp.route("/assuntos/<int:subject_id>/excluir", methods=["POST"])
def delete_subject(subject_id: int):
    row = query_one("SELECT discipline_id FROM subjects WHERE id = ?", (subject_id,))
    execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    flash("Assunto excluido.", "success")
    if row is None:
        return redirect(url_for("disciplines.index"))
    return redirect(url_for("disciplines.detail", discipline_id=row["discipline_id"]))


@bp.route("/api/assuntos")
def api_subjects():
    """Lista de assuntos de uma disciplina (usada pelos selects dinamicos)."""
    discipline_id = as_opt_int(request.args.get("discipline_id"))
    if not discipline_id:
        return {"subjects": []}
    rows = query_all("SELECT id, name FROM subjects WHERE discipline_id = ? ORDER BY name",
                     (discipline_id,))
    return {"subjects": [{"id": r["id"], "name": r["name"]} for r in rows]}


@bp.route("/ordenar", methods=["POST"])
def reorder():
    order = request.form.get("order", "")
    for position, raw in enumerate(order.split(","), start=1):
        did = as_int(raw, 0)
        if did:
            execute("UPDATE disciplines SET position = ? WHERE id = ?", (position, did))
    return {"ok": True}
