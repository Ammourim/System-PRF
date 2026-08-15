"""Simulados: registro, desempenho por disciplina, analise e cronometro."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, insert, query_all, query_one
from ..services import mocks as mocks_service
from ..services import settings as settings_service
from ..utils import as_int, as_opt_int, as_text, parse_minutes, percentage, today_iso
from .common import MISTAKE_CATEGORIES, disciplines, redirect_target

bp = Blueprint("mocks", __name__, url_prefix="/simulados")


@bp.route("/")
def index():
    rows = query_all("SELECT * FROM mock_exams ORDER BY date DESC, id DESC")
    series = [
        {"date": r["date"], "name": r["name"], "accuracy": r["percentage"]}
        for r in reversed(rows) if r["total"]
    ]
    return render_template(
        "mocks/index.html",
        mocks=rows,
        series=series,
        status=mocks_service.status(),
        frequency=settings_service.get("mock_frequency", "quinzenal"),
        default_minutes=settings_service.get_int("mock_default_minutes", 300),
        default_questions=settings_service.get_int("mock_default_questions", 120),
        today=today_iso(),
    )


@bp.route("/salvar", methods=["POST"])
def save():
    mock_id = as_opt_int(request.form.get("id"))
    total = as_int(request.form.get("total"), 0)
    correct = max(0, min(as_int(request.form.get("correct"), 0), total))
    values = (
        as_text(request.form.get("name"), "Simulado", max_length=120),
        as_text(request.form.get("date"), today_iso()),
        as_text(request.form.get("banca"), max_length=60),
        as_text(request.form.get("prova"), max_length=120),
        total, correct, total - correct, percentage(correct, total),
        parse_minutes(request.form.get("total_minutes"), 0),
        parse_minutes(request.form.get("planned_minutes"), 0),
        parse_minutes(request.form.get("time_left_minutes"), 0),
        as_text(request.form.get("slow_questions"), max_length=400),
        as_text(request.form.get("guessed_questions"), max_length=400),
        as_text(request.form.get("skipped_questions"), max_length=400),
        as_text(request.form.get("perception")),
        as_text(request.form.get("notes")),
    )
    if mock_id:
        execute(
            "UPDATE mock_exams SET name = ?, date = ?, banca = ?, prova = ?, total = ?,"
            " correct = ?, wrong = ?, percentage = ?, total_minutes = ?, planned_minutes = ?,"
            " time_left_minutes = ?, slow_questions = ?, guessed_questions = ?,"
            " skipped_questions = ?, perception = ?, notes = ? WHERE id = ?",
            values + (mock_id,))
        flash("Simulado atualizado.", "success")
    else:
        mock_id = insert(
            "INSERT INTO mock_exams (name, date, banca, prova, total, correct, wrong,"
            " percentage, total_minutes, planned_minutes, time_left_minutes, slow_questions,"
            " guessed_questions, skipped_questions, perception, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        # Fez o simulado: o aviso adiado nao faz mais sentido, o intervalo recomeca.
        mocks_service.clear_snooze()
        flash("Simulado registrado. Agora lance o desempenho por disciplina.", "success")
    return redirect(url_for("mocks.detail", mock_id=mock_id))


@bp.route("/<int:mock_id>")
def detail(mock_id: int):
    mock = query_one("SELECT * FROM mock_exams WHERE id = ?", (mock_id,))
    if mock is None:
        flash("Simulado nao encontrado.", "error")
        return redirect(url_for("mocks.index"))

    results = query_all(
        "SELECT r.*, d.name AS discipline_name, d.short_name, d.incidence"
        " FROM mock_exam_results r JOIN disciplines d ON d.id = r.discipline_id"
        " WHERE r.mock_exam_id = ? ORDER BY r.percentage DESC", (mock_id,))
    threshold_mid = settings_service.get_float("performance_mid", 70)
    strong = [r for r in results if r["percentage"] >= threshold_mid]
    weak = [r for r in results if r["percentage"] < threshold_mid]

    minutes_per_question = None
    if mock["total"] and mock["total_minutes"]:
        minutes_per_question = round(mock["total_minutes"] / mock["total"], 2)

    previous = query_one(
        "SELECT * FROM mock_exams WHERE date < ? OR (date = ? AND id < ?)"
        " ORDER BY date DESC, id DESC LIMIT 1", (mock["date"], mock["date"], mock_id))

    return render_template(
        "mocks/detail.html",
        mock=mock,
        results=results,
        strong=strong,
        weak=weak,
        minutes_per_question=minutes_per_question,
        previous=previous,
        delta_previous=round(mock["percentage"] - previous["percentage"], 1) if previous else None,
        disciplines=disciplines(),
        categories=MISTAKE_CATEGORIES,
        mistakes=query_all(
            "SELECT m.*, d.short_name, s.name AS subject_name FROM mistakes m"
            " LEFT JOIN disciplines d ON d.id = m.discipline_id"
            " LEFT JOIN subjects s ON s.id = m.subject_id"
            " WHERE m.mock_exam_id = ? ORDER BY m.id", (mock_id,)),
    )


@bp.route("/<int:mock_id>/resultado", methods=["POST"])
def save_result(mock_id: int):
    """Lanca/atualiza o desempenho de uma disciplina no simulado."""
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    if not discipline_id:
        flash("Selecione a disciplina.", "error")
        return redirect(url_for("mocks.detail", mock_id=mock_id))
    total = as_int(request.form.get("total"), 0)
    correct = max(0, min(as_int(request.form.get("correct"), 0), total))
    execute(
        "INSERT INTO mock_exam_results (mock_exam_id, discipline_id, total, correct, wrong,"
        " percentage, notes) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(mock_exam_id, discipline_id) DO UPDATE SET total = excluded.total,"
        " correct = excluded.correct, wrong = excluded.wrong,"
        " percentage = excluded.percentage, notes = excluded.notes",
        (mock_id, discipline_id, total, correct, total - correct, percentage(correct, total),
         as_text(request.form.get("notes"))))
    if request.form.get("recalc_total"):
        row = query_one(
            "SELECT COALESCE(SUM(total), 0) AS t, COALESCE(SUM(correct), 0) AS c"
            " FROM mock_exam_results WHERE mock_exam_id = ?", (mock_id,))
        execute(
            "UPDATE mock_exams SET total = ?, correct = ?, wrong = ?, percentage = ?"
            " WHERE id = ?",
            (row["t"], row["c"], row["t"] - row["c"], percentage(row["c"], row["t"]), mock_id))
    flash("Desempenho lancado.", "success")
    return redirect(url_for("mocks.detail", mock_id=mock_id))


@bp.route("/resultado/<int:result_id>/excluir", methods=["POST"])
def delete_result(result_id: int):
    row = query_one("SELECT mock_exam_id FROM mock_exam_results WHERE id = ?", (result_id,))
    execute("DELETE FROM mock_exam_results WHERE id = ?", (result_id,))
    if row is None:
        return redirect(url_for("mocks.index"))
    return redirect(url_for("mocks.detail", mock_id=row["mock_exam_id"]))


@bp.route("/<int:mock_id>/erro", methods=["POST"])
def add_mistake(mock_id: int):
    mock = query_one("SELECT date FROM mock_exams WHERE id = ?", (mock_id,))
    if mock is None:
        return redirect(url_for("mocks.index"))
    category = request.form.get("category", "C")
    insert(
        "INSERT INTO mistakes (date, discipline_id, subject_id, question_ref, category,"
        " explanation, status, mock_exam_id) VALUES (?, ?, NULL, ?, ?, ?, 'aberto', ?)",
        (mock["date"], as_opt_int(request.form.get("discipline_id")),
         as_text(request.form.get("question_ref"), max_length=400),
         category if category in MISTAKE_CATEGORIES else "C",
         as_text(request.form.get("explanation")), mock_id))
    flash("Erro do simulado registrado no caderno.", "success")
    return redirect(url_for("mocks.detail", mock_id=mock_id))


@bp.route("/<int:mock_id>/excluir", methods=["POST"])
def delete(mock_id: int):
    execute("DELETE FROM mock_exams WHERE id = ?", (mock_id,))
    flash("Simulado excluido.", "success")
    return redirect(redirect_target(url_for("mocks.index")))


@bp.route("/adiar", methods=["POST"])
def snooze():
    """Silencia o aviso de simulado por alguns dias. Nao muda a frequencia."""
    if request.form.get("action") == "clear":
        mocks_service.clear_snooze()
        flash("Aviso de simulado reativado.", "success")
    else:
        until = mocks_service.snooze(as_int(request.form.get("days"), 3))
        flash(f"Aviso de simulado adiado ate {until[8:10]}/{until[5:7]}. "
              "A frequencia configurada nao mudou.", "success")
    return redirect(redirect_target(url_for("dashboard.index")))


@bp.route("/cronometro")
def timer():
    """Modo PROVA REAL: cronometro em tela limpa, sem navegacao."""
    return render_template(
        "mocks/timer.html",
        default_minutes=settings_service.get_int("mock_default_minutes", 300),
        default_questions=settings_service.get_int("mock_default_questions", 120),
        today=today_iso(),
        disciplines=disciplines(),
    )
