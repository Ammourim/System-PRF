"""Configuracoes: metas, blocos, intervalos, limiares e dados de demonstracao."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..seed import clear_demo, has_demo, seed_demo
from ..services import settings as settings_service
from ..utils import as_float, as_int, as_text, parse_date, parse_minutes, to_iso

bp = Blueprint("settings", __name__, url_prefix="/configuracoes")

# Campo -> conversor. Tudo que a interface permite alterar passa por aqui.
FIELDS = {
    "cycle_days": as_int,
    "prf_goal_minutes": parse_minutes,
    "questions_goal_per_cycle": as_int,
    "questions_goal_per_folga": as_int,
    "cycle_goal_tolerance_pct": as_float,
    "cycle_min_block_minutes": parse_minutes,
    "block_long": parse_minutes,
    "block_medium": parse_minutes,
    "block_short": parse_minutes,
    "plantao_hours": as_float,
    "folga_hours": as_float,
    "plantoes_per_cycle": as_int,
    "folgas_per_cycle": as_int,
    "mock_default_minutes": parse_minutes,
    "mock_default_questions": as_int,
    "taf_minutes_per_cycle": parse_minutes,
    "college_hours_per_week": as_float,
    "performance_low": as_float,
    "performance_mid": as_float,
    "questions_split_new": as_int,
    "questions_split_review": as_int,
}

MOCK_FREQUENCIES = {"semanal": "Semanal", "quinzenal": "Quinzenal", "mensal": "Mensal",
                    "manual": "Manual"}


@bp.route("/")
def index():
    return render_template(
        "settings/index.html",
        settings=settings_service.all_settings(),
        frequencies=MOCK_FREQUENCIES,
        demo=has_demo(get_db()),
        database=current_app.config["DATABASE"],
        backup_dir=current_app.config["BACKUP_DIR"],
    )


@bp.route("/salvar", methods=["POST"])
def save():
    values: dict[str, object] = {}
    for key, convert in FIELDS.items():
        if key in request.form:
            values[key] = convert(request.form.get(key))

    # Listas de intervalos (PRF e faculdade): mesma validacao, listas separadas.
    for key, rotulo in (("review_intervals", "revisao"),
                        ("college_review_intervals", "revisao da faculdade")):
        if key not in request.form:
            continue
        parsed = []
        for part in as_text(request.form.get(key)).split(","):
            part = part.strip()
            if not part:
                continue
            value = as_int(part, 0)
            if value > 0:
                parsed.append(value)
        if parsed:
            values[key] = ",".join(str(v) for v in parsed)
        else:
            flash(f"Intervalos de {rotulo} invalidos - mantive os anteriores.", "error")

    # Prazo da faculdade: data ISO. Vazio ou invalido nao apaga o que existe.
    deadline = as_text(request.form.get("college_deadline"))
    if deadline:
        # Estrito: data que nao e ISO valida cairia em "hoje" e apagaria o prazo.
        if to_iso(parse_date(deadline)) == deadline:
            values["college_deadline"] = deadline
        else:
            flash("Prazo da faculdade invalido - mantive o anterior.", "error")

    frequency = request.form.get("mock_frequency")
    if frequency in MOCK_FREQUENCIES:
        values["mock_frequency"] = frequency

    if values:
        settings_service.set_many(values)
        flash("Configuracoes salvas.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/demo", methods=["POST"])
def demo():
    action = request.form.get("action")
    conn = get_db()
    if action == "clear":
        clear_demo(conn)
        flash("Dados de demonstracao removidos.", "success")
    elif action == "seed":
        seed_demo(conn)
        flash("Dados de demonstracao inseridos.", "success")
    return redirect(url_for("settings.index"))
