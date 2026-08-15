"""Ciclo adaptativo: gera SUGESTOES de ajuste. Nunca altera o ciclo sozinho.

Cada sugestao explica os numeros que a motivaram. O usuario aceita, ignora ou
ajusta manualmente - a decisao e sempre dele (regra 27 do projeto).
"""

from __future__ import annotations

from ..db import execute, query_all, scalar
from ..utils import days_between, today_iso
from . import mocks as mocks_service
from . import settings as settings_service, stats

# Passo de ajuste sugerido, em minutos por ciclo.
STEP_MINUTES = 30

# Abaixo disso o resultado do simulado nao e considerado (poucas questoes).
MIN_MOCK_QUESTIONS = 5


def _reasons(row: dict, low: float, mid: float, stale_days: int | None,
             mock: dict | None = None) -> tuple[str, list[str]]:
    """Decide a direcao (subir/manter/baixar) e lista os motivos.

    O simulado entra como um segundo sinal, com peso maior que a questao avulsa:
    foi feito sob pressao de tempo, entao um desempenho baixo la pesa mais.
    """
    reasons: list[str] = []
    direction = "manter"
    accuracy = row["accuracy"]
    incidence = row["incidence"] or 0
    questions = row["questions"] or 0

    mock_pct = None
    if mock and (mock["total"] or 0) >= MIN_MOCK_QUESTIONS:
        mock_pct = mock["percentage"]
        mock_note = (f"No simulado de {mock['mock_date'][8:10]}/{mock['mock_date'][5:7]}: "
                     f"{mock_pct:.0f}% ({mock['correct']}/{mock['total']}).")
    else:
        mock_note = None

    if row["status"] == "nao_iniciada":
        if row["target_minutes"] == 0:
            return "manter", ["Disciplina ainda nao iniciada e sem tempo alocado."]
        return "manter", ["Disciplina marcada como nao iniciada - contato progressivo."]

    # Sem questoes suficientes no dia a dia: o simulado vira o sinal principal.
    if accuracy is None or questions < 10:
        if mock_pct is not None:
            reasons.append(mock_note)
            if mock_pct < low:
                reasons.append(
                    f"Poucas questoes no periodo ({questions}), mas o simulado ja mostra "
                    f"desempenho abaixo de {low:.0f}%.")
                return "aumentar", reasons
            reasons.append(f"Poucas questoes no periodo ({questions}) - simulado dentro do "
                           "esperado, sem motivo para mexer.")
            return "manter", reasons

        reasons.append(
            f"Amostra pequena ({questions} questoes) - sem base para mudar a frequencia.")
        if stale_days is not None and stale_days >= 14:
            reasons.append(f"Sem estudo registrado ha {stale_days} dias.")
            direction = "aumentar"
        return direction, reasons

    if accuracy < low:
        direction = "aumentar"
        reasons.append(f"Aproveitamento {accuracy:.0f}% abaixo do limiar de {low:.0f}%.")
    elif accuracy < mid:
        reasons.append(f"Aproveitamento {accuracy:.0f}% na faixa de atencao.")
        if incidence >= 10:
            direction = "aumentar"
            reasons.append(f"Incidencia alta ({incidence:.2f}%) reforca a prioridade.")
    else:
        reasons.append(f"Aproveitamento {accuracy:.0f}% dentro do esperado.")
        if accuracy >= 85 and incidence < 6 and row["priority"] == "complementar":
            direction = "reduzir"
            reasons.append(
                f"Incidencia baixa ({incidence:.2f}%) e desempenho alto: da para "
                "realocar tempo sem perder terreno.")

    # O simulado pode reforcar, contradizer ou segurar a decisao.
    if mock_pct is not None:
        reasons.append(mock_note)
        if mock_pct < low and direction != "aumentar":
            direction = "aumentar"
            reasons.append("Vai bem nas questoes soltas, mas cai no simulado - sinal de "
                           "tempo/pressao, nao de conteudo.")
        elif mock_pct < mid and direction == "reduzir":
            direction = "manter"
            reasons.append("O simulado ainda nao confirma o bom desempenho: melhor nao "
                           "reduzir agora.")

    if stale_days is not None and stale_days >= 14 and direction != "aumentar":
        reasons.append(f"Sem estudo registrado ha {stale_days} dias.")
        direction = "aumentar"

    return direction, reasons


def suggestions(days: int = 60) -> list[dict]:
    low = settings_service.get_float("performance_low", 60)
    mid = settings_service.get_float("performance_mid", 70)
    reference = today_iso()
    rows = stats.by_discipline(days=days, reference=reference)
    mock_results = mocks_service.last_results_by_discipline()

    out = []
    for row in rows:
        stale = None
        if row["last_studied"]:
            stale = days_between(row["last_studied"], reference)
        mock = mock_results.get(row["id"])
        direction, reasons = _reasons(row, low, mid, stale, mock)

        current = int(row["target_minutes"] or 0)
        if direction == "aumentar":
            suggested = current + STEP_MINUTES
        elif direction == "reduzir":
            suggested = max(0, current - STEP_MINUTES)
        else:
            suggested = current

        out.append({
            "id": row["id"],
            "name": row["name"],
            "short_name": row["short_name"],
            "priority": row["priority"],
            "status": row["status"],
            "incidence": row["incidence"],
            "accuracy": row["accuracy"],
            "questions": row["questions"],
            "minutes": row["minutes"],
            "last_studied": row["last_studied"],
            "stale_days": stale,
            "mock_accuracy": mock["percentage"] if mock else None,
            "mock_date": mock["mock_date"] if mock else None,
            "current_target": current,
            "suggested_target": suggested,
            "delta": suggested - current,
            "direction": direction,
            "reasons": reasons,
        })

    order = {"aumentar": 0, "reduzir": 1, "manter": 2}
    out.sort(key=lambda r: (order[r["direction"]], -(r["incidence"] or 0)))
    return out


def apply_target(discipline_id: int, minutes: int) -> None:
    """Aplica a nova meta de minutos da disciplina (acao explicita do usuario)."""
    execute(
        "UPDATE disciplines SET target_minutes = ? WHERE id = ?",
        (max(0, int(minutes)), discipline_id),
    )


def totals() -> dict:
    total = int(scalar(
        "SELECT COALESCE(SUM(target_minutes), 0) FROM disciplines WHERE active = 1", (), 0))
    goal = settings_service.get_int("prf_goal_minutes", 1800)
    return {"target_total": total, "goal": goal, "delta": total - goal}


def cycle_report(cycle) -> dict:
    """Resumo de fechamento de ciclo (secao 45/46 do projeto)."""
    start, end = cycle["start_date"], cycle["end_date"]
    minutes = int(scalar(
        "SELECT COALESCE(SUM(actual_minutes), 0) FROM study_sessions"
        " WHERE date BETWEEN ? AND ?", (start, end), 0))
    questions_row = query_all(
        "SELECT COALESCE(SUM(total), 0) AS total, COALESCE(SUM(correct), 0) AS correct"
        " FROM questions WHERE date BETWEEN ? AND ?", (start, end))[0]
    total_q = int(questions_row["total"] or 0)
    correct_q = int(questions_row["correct"] or 0)

    top_disciplines = query_all(
        "SELECT d.name, SUM(s.actual_minutes) AS minutes FROM study_sessions s"
        " JOIN disciplines d ON d.id = s.discipline_id"
        " WHERE s.date BETWEEN ? AND ? GROUP BY d.id"
        " ORDER BY minutes DESC LIMIT 5", (start, end))
    mocks = query_all(
        "SELECT * FROM mock_exams WHERE date BETWEEN ? AND ? ORDER BY date", (start, end))
    reviews_done = int(scalar(
        "SELECT COUNT(*) FROM reviews WHERE last_done_at BETWEEN ? AND ?", (start, end), 0))
    reviews_pending = int(scalar(
        "SELECT COUNT(*) FROM reviews WHERE status = 'pendente' AND next_date <= ?", (end,), 0))
    from . import workouts as workouts_service

    workouts = workouts_service.count_in_period(start, end)
    college_minutes = int(scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM college_sessions WHERE date BETWEEN ? AND ?",
        (start, end), 0))

    goal = int(cycle["goal_minutes"] or 0)
    evolution = stats.discipline_evolution(
        days=max(1, days_between(start, end) + 1), reference=end)
    improved = [e for e in evolution if e["delta"] is not None and e["delta"] > 0]
    worsened = [e for e in evolution if e["delta"] is not None and e["delta"] < 0]

    return {
        "cycle": cycle,
        "minutes": minutes,
        "goal_minutes": goal,
        "minutes_pct": round(minutes / goal * 100, 1) if goal else 0.0,
        "questions": total_q,
        "goal_questions": int(cycle["goal_questions"] or 0),
        "accuracy": round(correct_q / total_q * 100, 1) if total_q else None,
        "top_disciplines": [dict(r) for r in top_disciplines],
        "mocks": [dict(r) for r in mocks],
        "reviews_done": reviews_done,
        "reviews_pending": reviews_pending,
        "workouts": workouts,
        "college_minutes": college_minutes,
        "weak_points": stats.weak_points(days=max(1, days_between(start, end) + 1), limit=5),
        "best_evolution": improved[0] if improved else None,
        "worst_evolution": worsened[-1] if worsened else None,
        "suggestions": suggestions(days=max(1, days_between(start, end) + 1))[:5],
    }
