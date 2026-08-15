"""Treinos do TAF: plano, exercicios, execucao e historico.

Separado de `taf.py` (que cuida dos testes e das marcas) para nao concentrar
areas diferentes no mesmo arquivo. Toda a regra vive em services/workouts.py -
aqui so lemos formulario, chamamos o servico e renderizamos.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services import workouts as service
from ..utils import (as_float, as_int, as_opt_int, as_text, parse_minutes, today_iso)
from .common import redirect_target

bp = Blueprint("workouts", __name__, url_prefix="/taf/treinos")


def _segundos(campo: str) -> int | None:
    """Segundos a partir de '90' ou de 'm:ss' ('1:30' = 90s).

    parse_minutes('1:30') devolve 1*60+30 = 90, que e exatamente o total em
    segundos quando lemos o valor como minuto:segundo. Vazio vira None, porque
    todo campo de prescricao e opcional.
    """
    bruto = as_text(request.form.get(campo))
    if not bruto:
        return None
    if ":" in bruto:
        return parse_minutes(bruto) or None
    return as_int(bruto, 0) or None


def _prescricao() -> dict:
    """Le os campos de prescricao. Todos opcionais - cada exercicio usa os seus."""
    distancia = as_float(request.form.get("distance_km"), None)
    minutos_total = as_text(request.form.get("total_minutes"))
    return {
        "category": (request.form.get("category")
                     if request.form.get("category") in service.CATEGORIES else "outro"),
        "sets": as_opt_int(request.form.get("sets")),
        "reps": as_opt_int(request.form.get("reps")),
        "seconds_per_set": _segundos("seconds_per_set"),
        "distance_km": distancia if distancia else None,
        "total_seconds": (parse_minutes(minutos_total) * 60) if minutos_total else None,
        "rest_seconds": _segundos("rest_seconds"),
        "goal": as_text(request.form.get("goal"), max_length=160),
        "notes": as_text(request.form.get("notes")),
    }


# ==========================================================================
# Plano
# ==========================================================================
@bp.route("/")
def index():
    return render_template(
        "workouts/index.html",
        workouts=service.list_workouts(status=None),
        types=service.WORKOUT_TYPES,
        statuses=service.PLAN_STATUS,
        open_session=service.open_session(),
        recent=service.sessions(limit=8, status="concluida"),
        today=today_iso(),
    )


@bp.route("/salvar", methods=["POST"])
def save():
    workout_id = as_opt_int(request.form.get("id"))
    nome = as_text(request.form.get("name"), max_length=120)
    if not nome:
        flash("Informe o nome do treino.", "error")
        return redirect(redirect_target(url_for("workouts.index")))

    tipo = request.form.get("type")
    status = request.form.get("status", "ativo")
    campos = {
        "objective": as_text(request.form.get("objective"), max_length=300),
        "type": tipo if tipo in service.WORKOUT_TYPES else "outro",
        "duration_minutes": parse_minutes(request.form.get("duration_minutes"), 0),
        "start_date": as_text(request.form.get("start_date")) or None,
        "end_date": as_text(request.form.get("end_date")) or None,
        "status": status if status in service.PLAN_STATUS else "ativo",
        "notes": as_text(request.form.get("notes")),
    }

    if workout_id:
        service.update_workout(workout_id, nome, **campos)
        flash("Treino atualizado.", "success")
    else:
        workout_id = service.create_workout(nome, **campos)
        flash("Treino criado. Agora cadastre os exercicios.", "success")
    return redirect(url_for("workouts.detail", workout_id=workout_id))


@bp.route("/<int:workout_id>")
def detail(workout_id: int):
    treino = service.get_workout(workout_id)
    if treino is None:
        flash("Treino nao encontrado.", "error")
        return redirect(url_for("workouts.index"))
    itens = service.exercises(workout_id)
    return render_template(
        "workouts/detail.html",
        workout=treino,
        exercises=[{"row": e, "summary": service.describe_prescription(e)} for e in itens],
        types=service.WORKOUT_TYPES,
        statuses=service.PLAN_STATUS,
        categories=service.CATEGORIES,
        history=service.sessions(limit=15, workout_id=workout_id),
        open_session=service.open_session(),
        today=today_iso(),
    )


@bp.route("/<int:workout_id>/excluir", methods=["POST"])
def delete(workout_id: int):
    service.delete_workout(workout_id)
    flash("Treino excluido. O historico de execucoes foi preservado.", "success")
    return redirect(url_for("workouts.index"))


# ==========================================================================
# Exercicios
# ==========================================================================
@bp.route("/<int:workout_id>/exercicios/novo")
def new_exercise(workout_id: int):
    treino = service.get_workout(workout_id)
    if treino is None:
        flash("Treino nao encontrado.", "error")
        return redirect(url_for("workouts.index"))
    return render_template("workouts/exercise_form.html", workout=treino, exercise=None,
                           categories=service.CATEGORIES,
                           position=service.next_position(workout_id))


@bp.route("/exercicios/<int:exercise_id>/editar")
def edit_exercise(exercise_id: int):
    item = service.get_exercise(exercise_id)
    if item is None:
        flash("Exercicio nao encontrado.", "error")
        return redirect(url_for("workouts.index"))
    return render_template("workouts/exercise_form.html",
                           workout=service.get_workout(item["workout_id"]),
                           exercise=item, categories=service.CATEGORIES,
                           position=item["position"])


@bp.route("/<int:workout_id>/exercicios/salvar", methods=["POST"])
def save_exercise(workout_id: int):
    exercise_id = as_opt_int(request.form.get("id"))
    nome = as_text(request.form.get("name"), max_length=120)
    if not nome:
        flash("Informe o nome do exercicio.", "error")
        return redirect(url_for("workouts.new_exercise", workout_id=workout_id))

    campos = _prescricao()
    if exercise_id:
        service.update_exercise(exercise_id, nome, **campos)
        flash(f"Exercicio '{nome}' atualizado.", "success")
    else:
        service.add_exercise(workout_id, nome, **campos)
        flash(f"Exercicio '{nome}' adicionado.", "success")

    if request.form.get("add_another"):
        return redirect(url_for("workouts.new_exercise", workout_id=workout_id))
    return redirect(url_for("workouts.detail", workout_id=workout_id))


@bp.route("/exercicios/<int:exercise_id>/acao", methods=["POST"])
def exercise_action(exercise_id: int):
    item = service.get_exercise(exercise_id)
    if item is None:
        flash("Exercicio nao encontrado.", "error")
        return redirect(url_for("workouts.index"))
    workout_id = item["workout_id"]
    acao = request.form.get("action")

    if acao == "subir":
        service.move_exercise(exercise_id, -1)
    elif acao == "descer":
        service.move_exercise(exercise_id, 1)
    elif acao == "duplicar":
        service.duplicate_exercise(exercise_id)
        flash("Exercicio duplicado.", "success")
    elif acao == "excluir":
        service.delete_exercise(exercise_id)
        flash("Exercicio removido do treino. As execucoes anteriores foram mantidas.",
              "success")
    return redirect(url_for("workouts.detail", workout_id=workout_id))


# ==========================================================================
# Execucao
# ==========================================================================
@bp.route("/<int:workout_id>/iniciar", methods=["POST"])
def start(workout_id: int):
    aberta = service.open_session()
    if aberta is not None:
        flash("Ja existe um treino em andamento. Conclua ou abandone antes de iniciar outro.",
              "error")
        return redirect(url_for("workouts.run", session_id=aberta["id"]))

    session_id = service.start_session(workout_id)
    if session_id is None:
        flash("Cadastre pelo menos um exercicio antes de iniciar o treino.", "error")
        return redirect(url_for("workouts.detail", workout_id=workout_id))
    return redirect(url_for("workouts.run", session_id=session_id))


@bp.route("/execucao/<int:session_id>")
def run(session_id: int):
    sessao = service.get_session(session_id)
    if sessao is None:
        flash("Execucao nao encontrada.", "error")
        return redirect(url_for("workouts.index"))

    if sessao["status"] != "em_andamento":
        return redirect(url_for("workouts.session_detail", session_id=session_id))

    atual = service.current_exercise(session_id)
    resumo = service.session_summary(session_id)
    return render_template(
        "workouts/run.html",
        session=sessao,
        current=atual,
        progress=service.exercise_progress(atual) if atual else None,
        summary=resumo,
        position=([e["exercise"]["id"] for e in resumo["exercises"]].index(atual["id"]) + 1
                  if atual else resumo["total_exercises"]),
    )


@bp.route("/execucao/<int:session_id>/serie", methods=["POST"])
def log_set(session_id: int):
    session_exercise_id = as_opt_int(request.form.get("session_exercise_id"))
    if not session_exercise_id:
        return redirect(url_for("workouts.run", session_id=session_id))

    distancia = as_float(request.form.get("distance_km"), None)
    service.log_set(
        session_exercise_id,
        set_number=as_opt_int(request.form.get("set_number")),
        reps=as_opt_int(request.form.get("reps")),
        seconds=_segundos("seconds"),
        distance_km=distancia if distancia else None,
        notes=as_text(request.form.get("notes"), max_length=200),
    )

    # Bateu o numero de series previstas? Entao o exercicio terminou.
    item = service.get_session_exercise(session_exercise_id)
    if item is not None:
        progresso = service.exercise_progress(item)
        if progresso["sets_planned"] and progresso["sets_done"] >= progresso["sets_planned"]:
            service.set_exercise_status(session_exercise_id, "concluido")
            flash(f"{item['name']} concluido: "
                  f"{progresso['achieved']}/{progresso['target']} {progresso['unit']}.",
                  "success")
    return redirect(url_for("workouts.run", session_id=session_id))


@bp.route("/execucao/<int:session_id>/exercicio", methods=["POST"])
def exercise_status(session_id: int):
    session_exercise_id = as_opt_int(request.form.get("session_exercise_id"))
    status = request.form.get("status", "concluido")
    if session_exercise_id:
        service.set_exercise_status(session_exercise_id, status)
        flash("Exercicio pulado." if status == "pulado" else "Exercicio concluido.",
              "success")
    return redirect(url_for("workouts.run", session_id=session_id))


@bp.route("/execucao/<int:session_id>/serie/<int:set_id>/excluir", methods=["POST"])
def delete_set(session_id: int, set_id: int):
    service.delete_set(set_id)
    flash("Serie removida.", "success")
    return redirect(url_for("workouts.run", session_id=session_id))


@bp.route("/execucao/<int:session_id>/encerrar", methods=["POST"])
def finish(session_id: int):
    status = request.form.get("status", "concluida")
    service.finish_session(
        session_id, status=status,
        notes=as_text(request.form.get("notes")) or None,
        minutes=parse_minutes(request.form.get("duration_minutes"), None)
        if request.form.get("duration_minutes") else None)
    flash("Treino concluido." if status == "concluida" else "Treino encerrado.", "success")
    return redirect(url_for("workouts.session_detail", session_id=session_id))


@bp.route("/execucao/<int:session_id>/resumo")
def session_detail(session_id: int):
    resumo = service.session_summary(session_id)
    if not resumo:
        flash("Execucao nao encontrada.", "error")
        return redirect(url_for("workouts.index"))
    return render_template("workouts/session.html", **resumo,
                           statuses=service.SESSION_STATUS)


@bp.route("/execucao/<int:session_id>/excluir", methods=["POST"])
def delete_session(session_id: int):
    service.delete_session(session_id)
    flash("Execucao excluida do historico.", "success")
    return redirect(redirect_target(url_for("workouts.index")))


@bp.route("/historico")
def history():
    return render_template("workouts/history.html",
                           sessions=service.sessions(limit=100),
                           statuses=service.SESSION_STATUS)
