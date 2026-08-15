"""Ciclo de estudos: visualizacao, montagem manual, avanco e relatorio."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, query_all, query_one
from ..services import adaptive
from ..services import cycle as cycle_service
from ..services import settings as settings_service
from ..utils import as_bool, as_int, as_opt_int, as_text, parse_minutes, today_iso
from .common import disciplines, redirect_target, subjects

bp = Blueprint("cycles", __name__, url_prefix="/ciclo")


@bp.route("/")
def index():
    cycle = cycle_service.active_cycle()
    if cycle is None:
        return render_template("cycles/index.html", cycle=None, blocks=[], progress={},
                               history=query_all(
                                   "SELECT * FROM study_cycles ORDER BY number DESC"))
    return render_template(
        "cycles/index.html",
        cycle=cycle,
        blocks=cycle_service.blocks(cycle["id"]),
        progress=cycle_service.progress(cycle),
        capacity=cycle_service.estimated_capacity(),
        history=query_all("SELECT * FROM study_cycles ORDER BY number DESC"),
        subjects=subjects(),
        disciplines=disciplines(),
    )


@bp.route("/montar", methods=["GET", "POST"])
def build():
    """Monta o plano do proximo ciclo. Tudo editavel antes de gerar."""
    rows = disciplines()
    if request.method == "POST":
        plan = []
        for row in rows:
            target = parse_minutes(request.form.get(f"target_{row['id']}"), 0)
            block = parse_minutes(request.form.get(f"block_{row['id']}"), row["block_minutes"])
            block = max(5, block)
            execute(
                "UPDATE disciplines SET target_minutes = ?, block_minutes = ? WHERE id = ?",
                (target, block, row["id"]))
            if target > 0:
                plan.append({
                    "discipline_id": row["id"],
                    "name": row["name"],
                    "block_minutes": block,
                    "target_minutes": target,
                    "count": max(1, int(target / block + 0.5)),
                })
        if not plan:
            flash("Defina pelo menos uma disciplina com meta maior que zero.", "error")
            return redirect(url_for("cycles.build"))

        goal = parse_minutes(request.form.get("goal_minutes"),
                             settings_service.get_int("prf_goal_minutes", 1800))
        goal_questions = as_int(request.form.get("goal_questions"),
                                settings_service.get_int("questions_goal_per_cycle", 350))
        days = as_int(request.form.get("days"), settings_service.get_int("cycle_days", 14))

        if as_bool(request.form.get("rebuild_current")):
            cycle = cycle_service.active_cycle()
            if cycle is None:
                flash("Nao ha ciclo ativo para regerar.", "error")
                return redirect(url_for("cycles.build"))
            total = cycle_service.rebuild_blocks(cycle["id"], plan)
            execute(
                "UPDATE study_cycles SET goal_minutes = ?, goal_questions = ? WHERE id = ?",
                (goal, goal_questions, cycle["id"]))
            flash(f"Blocos do ciclo atual regerados ({total} blocos). Posicao voltou para 1.",
                  "success")
        else:
            cycle_id = cycle_service.create_cycle(
                plan, start_date=as_text(request.form.get("start_date"), today_iso()),
                name=as_text(request.form.get("name")), goal_minutes=goal,
                goal_questions=goal_questions, days=days)
            total = cycle_service.total_blocks(cycle_id)
            flash(f"Novo ciclo criado com {total} blocos.", "success")
        return redirect(url_for("cycles.index"))

    preview_plan = cycle_service.spread(cycle_service.plan_from_disciplines(rows))
    planned_minutes = sum(int(i["block_minutes"]) for i in preview_plan)
    return render_template(
        "cycles/build.html",
        disciplines=rows,
        preview=preview_plan,
        planned_minutes=planned_minutes,
        goal_minutes=settings_service.get_int("prf_goal_minutes", 1800),
        goal_questions=settings_service.get_int("questions_goal_per_cycle", 350),
        days=settings_service.get_int("cycle_days", 14),
        block_sizes=settings_service.block_sizes(),
        capacity=cycle_service.estimated_capacity(),
        has_active=cycle_service.active_cycle() is not None,
    )


@bp.route("/avancar", methods=["POST"])
def advance():
    cycle = cycle_service.active_cycle()
    if cycle is None:
        flash("Nenhum ciclo ativo.", "error")
        return redirect(url_for("cycles.index"))
    block_id = as_opt_int(request.form.get("block_id"))
    mark_done = as_bool(request.form.get("mark_done") or "1")
    cycle_service.advance(cycle["id"], block_id, mark_done=mark_done)
    flash("Bloco concluido." if mark_done else "Bloco adiado (sem marcar como feito).",
          "success")
    return redirect(redirect_target(url_for("dashboard.index")))


@bp.route("/posicao", methods=["POST"])
def set_position():
    cycle = cycle_service.active_cycle()
    if cycle is None:
        return redirect(url_for("cycles.index"))
    cycle_service.set_position(cycle["id"], as_int(request.form.get("position"), 1))
    flash("Posicao do ciclo ajustada manualmente.", "success")
    return redirect(redirect_target(url_for("cycles.index")))


@bp.route("/bloco/<int:block_id>", methods=["POST"])
def update_block(block_id: int):
    action = request.form.get("action", "update")
    if action == "toggle":
        cycle_service.toggle_block_done(block_id)
    elif action == "delete":
        execute("DELETE FROM cycle_blocks WHERE id = ?", (block_id,))
        flash("Bloco removido do ciclo.", "success")
    else:
        block = query_one("SELECT * FROM cycle_blocks WHERE id = ?", (block_id,))
        if block is None:
            flash("Bloco nao encontrado.", "error")
            return redirect(url_for("cycles.index"))
        minutes = max(5, parse_minutes(request.form.get("planned_minutes"),
                                       block["planned_minutes"]))
        execute(
            "UPDATE cycle_blocks SET discipline_id = ?, subject_id = ?, planned_minutes = ?,"
            " block_size = ?, focus = ? WHERE id = ?",
            (as_opt_int(request.form.get("discipline_id")) or block["discipline_id"],
             as_opt_int(request.form.get("subject_id")), minutes,
             settings_service.block_size_name(minutes),
             as_text(request.form.get("focus"), max_length=200), block_id))
    return redirect(redirect_target(url_for("cycles.index")))


@bp.route("/bloco/novo", methods=["POST"])
def add_block():
    cycle = cycle_service.active_cycle()
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    if cycle is None or not discipline_id:
        flash("Selecione uma disciplina.", "error")
        return redirect(url_for("cycles.index"))
    row = query_one(
        "SELECT COALESCE(MAX(position), 0) AS p FROM cycle_blocks WHERE cycle_id = ?",
        (cycle["id"],))
    minutes = max(5, parse_minutes(request.form.get("planned_minutes"), 60))
    execute(
        "INSERT INTO cycle_blocks (cycle_id, position, discipline_id, subject_id,"
        " planned_minutes, block_size, focus) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cycle["id"], int(row["p"]) + 1, discipline_id,
         as_opt_int(request.form.get("subject_id")), minutes,
         settings_service.block_size_name(minutes),
         as_text(request.form.get("focus"), max_length=200)))
    flash("Bloco adicionado ao fim do ciclo.", "success")
    return redirect(url_for("cycles.index"))


@bp.route("/<int:cycle_id>/relatorio")
def report(cycle_id: int):
    cycle = query_one("SELECT * FROM study_cycles WHERE id = ?", (cycle_id,))
    if cycle is None:
        flash("Ciclo nao encontrado.", "error")
        return redirect(url_for("cycles.index"))
    return render_template("cycles/report.html", report=adaptive.cycle_report(cycle),
                           cycle=cycle)


@bp.route("/<int:cycle_id>/encerrar", methods=["POST"])
def close(cycle_id: int):
    cycle_service.close_cycle(cycle_id)
    flash("Ciclo encerrado. Veja o relatorio e monte o proximo quando quiser.", "success")
    return redirect(url_for("cycles.report", cycle_id=cycle_id))


@bp.route("/<int:cycle_id>/reabrir", methods=["POST"])
def reopen(cycle_id: int):
    cycle_service.reopen_cycle(cycle_id)
    flash("Ciclo reaberto.", "success")
    return redirect(url_for("cycles.index"))
