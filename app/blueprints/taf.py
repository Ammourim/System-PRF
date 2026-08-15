"""TAF: testes, marcas, evolucao e planejamento de treinos.

Organizador de treino - nao emite prescricao ou orientacao medica.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one, scalar
from ..services import settings as settings_service
from ..utils import add_days, as_bool, as_float, as_int, as_opt_int, as_text, today_iso
from .common import redirect_target

bp = Blueprint("taf", __name__, url_prefix="/taf")

WORKOUT_TYPES = {"corrida": "Corrida", "forca": "Forca", "misto": "Misto", "outro": "Outro"}
WORKOUT_STATUS = {"planejado": "Planejado", "concluido": "Concluido", "pendente": "Pendente"}


def _progress(test) -> float | None:
    current, goal = test["current_mark"], test["goal_mark"]
    if current is None or goal in (None, 0):
        return None
    if test["higher_is_better"]:
        return round(min(current / goal * 100, 999), 1)
    return round(min(goal / current * 100, 999), 1) if current else None


@bp.route("/")
def index():
    tests = query_all("SELECT * FROM taf_tests WHERE active = 1 ORDER BY id")
    data = []
    for test in tests:
        history = query_all(
            "SELECT * FROM taf_measurements WHERE test_id = ? ORDER BY date", (test["id"],))
        delta = None
        if len(history) >= 2 and history[0]["value"]:
            delta = round((history[-1]["value"] - history[0]["value"])
                          / history[0]["value"] * 100, 1)
            if not test["higher_is_better"]:
                delta = -delta
        data.append({"test": test, "history": history, "progress": _progress(test),
                     "delta": delta})

    today = today_iso()
    minutes_cycle = int(scalar(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM taf_workouts"
        " WHERE status = 'concluido' AND date >= ?", (add_days(today, -14),), 0))

    return render_template(
        "taf/index.html",
        tests=data,
        upcoming=query_all(
            "SELECT * FROM taf_workouts WHERE date >= ? AND status = 'planejado'"
            " ORDER BY date LIMIT 10", (today,)),
        pending=query_all(
            "SELECT * FROM taf_workouts WHERE status = 'pendente'"
            " OR (status = 'planejado' AND date < ?) ORDER BY date DESC LIMIT 10", (today,)),
        recent=query_all(
            "SELECT * FROM taf_workouts WHERE status = 'concluido' ORDER BY date DESC LIMIT 10"),
        workout_types=WORKOUT_TYPES,
        workout_status=WORKOUT_STATUS,
        goal_minutes=settings_service.get_int("taf_minutes_per_cycle", 420),
        minutes_cycle=minutes_cycle,
        today=today,
    )


# --------------------------------------------------------------------------
# Testes e marcas
# --------------------------------------------------------------------------
@bp.route("/testes/salvar", methods=["POST"])
def save_test():
    test_id = as_opt_int(request.form.get("id"))
    values = (as_text(request.form.get("name"), max_length=80),
              as_text(request.form.get("unit"), max_length=30),
              as_float(request.form.get("goal_mark"), None),
              as_bool(request.form.get("higher_is_better")),
              as_text(request.form.get("notes")))
    if test_id:
        execute(
            "UPDATE taf_tests SET name = ?, unit = ?, goal_mark = ?, higher_is_better = ?,"
            " notes = ? WHERE id = ?", values + (test_id,))
        flash("Teste atualizado.", "success")
    else:
        if not values[0]:
            flash("Informe o nome do teste.", "error")
            return redirect(url_for("taf.index"))
        insert(
            "INSERT INTO taf_tests (name, unit, goal_mark, higher_is_better, notes)"
            " VALUES (?, ?, ?, ?, ?)", values)
        flash("Teste cadastrado.", "success")
    return redirect(redirect_target(url_for("taf.index")))


@bp.route("/testes/<int:test_id>/marca", methods=["POST"])
def add_measurement(test_id: int):
    value = as_float(request.form.get("value"), None)
    if value is None:
        flash("Informe a marca medida.", "error")
        return redirect(url_for("taf.index"))
    date = as_text(request.form.get("date"), today_iso())
    insert("INSERT INTO taf_measurements (test_id, date, value, notes) VALUES (?, ?, ?, ?)",
           (test_id, date, value, as_text(request.form.get("notes"))))
    latest = query_one(
        "SELECT value, date FROM taf_measurements WHERE test_id = ?"
        " ORDER BY date DESC, id DESC LIMIT 1", (test_id,))
    if latest:
        execute("UPDATE taf_tests SET current_mark = ?, measured_at = ? WHERE id = ?",
                (latest["value"], latest["date"], test_id))
    flash("Marca registrada.", "success")
    return redirect(redirect_target(url_for("taf.index")))


@bp.route("/testes/<int:test_id>/excluir", methods=["POST"])
def delete_test(test_id: int):
    execute("UPDATE taf_tests SET active = 0 WHERE id = ?", (test_id,))
    flash("Teste desativado (o historico foi preservado).", "success")
    return redirect(url_for("taf.index"))


# --------------------------------------------------------------------------
# Treinos
# --------------------------------------------------------------------------
@bp.route("/treinos")
def workouts():
    start = request.args.get("start") or add_days(today_iso(), -30)
    end = request.args.get("end") or add_days(today_iso(), 30)
    return render_template(
        "taf/workouts.html",
        workouts=query_all(
            "SELECT * FROM taf_workouts WHERE date BETWEEN ? AND ? ORDER BY date DESC",
            (start, end)),
        workout_types=WORKOUT_TYPES,
        workout_status=WORKOUT_STATUS,
        start=start, end=end, today=today_iso(),
    )


@bp.route("/treinos/salvar", methods=["POST"])
def save_workout():
    workout_id = as_opt_int(request.form.get("id"))
    kind = request.form.get("type", "corrida")
    status = request.form.get("status", "planejado")
    values = (as_text(request.form.get("date"), today_iso()),
              as_text(request.form.get("name"), max_length=80),
              kind if kind in WORKOUT_TYPES else "outro",
              as_int(request.form.get("duration_minutes"), 0),
              as_text(request.form.get("exercise"), max_length=400),
              as_opt_int(request.form.get("sets")), as_opt_int(request.form.get("reps")),
              as_float(request.form.get("distance_km"), None),
              as_text(request.form.get("time_text"), max_length=40),
              status if status in WORKOUT_STATUS else "planejado",
              as_text(request.form.get("notes")))
    if workout_id:
        execute(
            "UPDATE taf_workouts SET date = ?, name = ?, type = ?, duration_minutes = ?,"
            " exercise = ?, sets = ?, reps = ?, distance_km = ?, time_text = ?, status = ?,"
            " notes = ? WHERE id = ?", values + (workout_id,))
        flash("Treino atualizado.", "success")
    else:
        insert(
            "INSERT INTO taf_workouts (date, name, type, duration_minutes, exercise, sets,"
            " reps, distance_km, time_text, status, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        flash("Treino cadastrado.", "success")
    return redirect(redirect_target(url_for("taf.workouts")))


@bp.route("/treinos/<int:workout_id>/status", methods=["POST"])
def workout_status(workout_id: int):
    status = request.form.get("status", "concluido")
    if status in WORKOUT_STATUS:
        execute("UPDATE taf_workouts SET status = ? WHERE id = ?", (status, workout_id))
        flash(f"Treino marcado como {WORKOUT_STATUS[status].lower()}.", "success")
    return redirect(redirect_target(url_for("taf.index")))


@bp.route("/treinos/<int:workout_id>/remarcar", methods=["POST"])
def reschedule(workout_id: int):
    """Remarcacao sempre manual: treino perdido nunca vira uma fila impossivel."""
    date = as_text(request.form.get("date"), "")
    if not date:
        date = add_days(today_iso(), as_int(request.form.get("days"), 1))
    execute("UPDATE taf_workouts SET date = ?, status = 'planejado' WHERE id = ?",
            (date, workout_id))
    flash("Treino remarcado.", "success")
    return redirect(redirect_target(url_for("taf.index")))


@bp.route("/treinos/<int:workout_id>/excluir", methods=["POST"])
def delete_workout(workout_id: int):
    execute("DELETE FROM taf_workouts WHERE id = ?", (workout_id,))
    flash("Treino excluido.", "success")
    return redirect(redirect_target(url_for("taf.workouts")))
