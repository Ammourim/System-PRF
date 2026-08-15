"""TAF: testes, marcas e evolucao.

Os treinos (plano, exercicios, execucao e historico) ficam em
`blueprints/workouts.py`, para nao juntar duas areas no mesmo arquivo.

Organizador de treino - nao emite prescricao ou orientacao medica.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one
from ..services import settings as settings_service
from ..services import workouts as workouts_service
from ..utils import add_days, as_bool, as_float, as_opt_int, as_text, today_iso
from .common import redirect_target

bp = Blueprint("taf", __name__, url_prefix="/taf")


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
    minutes_cycle = workouts_service.minutes_in_period(add_days(today, -13), today)

    return render_template(
        "taf/index.html",
        tests=data,
        active_workouts=workouts_service.active_today(today),
        open_session=workouts_service.open_session(),
        recent=workouts_service.sessions(limit=8, status="concluida"),
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
