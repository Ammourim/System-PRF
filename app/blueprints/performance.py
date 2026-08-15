"""Desempenho: visao geral, por disciplina, por assunto e sugestoes de ajuste."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services import adaptive
from ..services import settings as settings_service
from ..services import stats
from ..utils import as_int, as_opt_int, parse_minutes
from .common import MISTAKE_CATEGORIES, redirect_target

bp = Blueprint("performance", __name__, url_prefix="/desempenho")


@bp.route("/")
def index():
    days = as_int(request.args.get("days"), 30) or 30
    return render_template(
        "performance/index.html",
        days=days,
        overall=stats.overall(days=days),
        evolution=stats.evolution(days=days),
        by_discipline=stats.by_discipline(days=days),
        discipline_evolution=stats.discipline_evolution(days=days),
        by_subject=stats.by_subject(days=days, min_questions=5, limit=40),
        weak_subjects=stats.weak_points(days=days, limit=10, min_questions=5),
        series=stats.daily_series(days=min(days, 90)),
        mistakes=stats.mistakes_by_category(days=days),
        mistake_categories=MISTAKE_CATEGORIES,
        thresholds={
            "low": settings_service.get_float("performance_low", 60),
            "mid": settings_service.get_float("performance_mid", 70),
        },
    )


@bp.route("/ajustes")
def adjustments():
    days = as_int(request.args.get("days"), 60) or 60
    return render_template(
        "performance/adjustments.html",
        days=days,
        suggestions=adaptive.suggestions(days=days),
        totals=adaptive.totals(),
        step=adaptive.STEP_MINUTES,
    )


@bp.route("/ajustes/aplicar", methods=["POST"])
def apply_adjustment():
    """Aplica UMA sugestao - sempre por acao explicita do usuario."""
    discipline_id = as_opt_int(request.form.get("discipline_id"))
    minutes = parse_minutes(request.form.get("minutes"), -1)
    if not discipline_id or minutes < 0:
        flash("Nao foi possivel aplicar o ajuste.", "error")
        return redirect(url_for("performance.adjustments"))
    adaptive.apply_target(discipline_id, minutes)
    flash("Meta da disciplina atualizada. Regere os blocos do ciclo quando quiser aplicar.",
          "success")
    return redirect(redirect_target(url_for("performance.adjustments")))
