"""Dashboard: proximo bloco, hoje, ciclo, desempenho e atencao."""

from __future__ import annotations

from flask import Blueprint, render_template

from ..db import query_all
from ..services import cycle as cycle_service
from ..services import mocks as mocks_service
from ..services import reviews as reviews_service
from ..services import settings as settings_service
from ..services import stats
from ..utils import add_days, today_iso
from .common import SESSION_TYPES, disciplines

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    cycle = cycle_service.active_cycle()
    progress = cycle_service.progress(cycle)
    block = cycle_service.next_block(cycle)
    today = today_iso()

    pending_workouts = query_all(
        "SELECT * FROM taf_workouts WHERE status = 'pendente' ORDER BY date DESC LIMIT 3")
    next_workout = query_all(
        "SELECT * FROM taf_workouts WHERE status = 'planejado' AND date >= ?"
        " ORDER BY date LIMIT 1", (today,))
    college_due = query_all(
        "SELECT t.*, c.name AS subject_name FROM college_tasks t"
        " LEFT JOIN college_subjects c ON c.id = t.college_subject_id"
        " WHERE t.status = 'aberta' AND (t.due_date IS NULL OR t.due_date <= ?)"
        " ORDER BY t.due_date LIMIT 4", (add_days(today, 14),))

    return render_template(
        "dashboard/index.html",
        cycle=cycle,
        progress=progress,
        block=block,
        upcoming_blocks=cycle_service.upcoming(cycle, limit=4),
        due_reviews=reviews_service.due(limit=6),
        review_counts=reviews_service.counts(),
        today_summary=stats.today_summary(),
        evolution=stats.evolution(days=30),
        overall=stats.overall(days=30),
        weak_subjects=stats.weak_points(days=90, limit=4),
        weak_disciplines=stats.weak_disciplines(days=90, limit=3),
        disciplines=disciplines(),
        session_types=SESSION_TYPES,
        capacity=cycle_service.estimated_capacity(),
        mock_status=mocks_service.status(),
        pending_workouts=pending_workouts,
        next_workout=next_workout[0] if next_workout else None,
        college_due=college_due,
        college_goal_minutes=int(settings_service.get_float("college_hours_per_week", 4) * 60),
    )
