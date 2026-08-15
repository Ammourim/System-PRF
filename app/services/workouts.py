"""Treinos do TAF: plano, prescricao, execucao e historico.

Separacao proposital:
  * PLANO      (taf_workouts + taf_workout_exercises) - o que voce pretende fazer;
  * EXECUCAO   (taf_workout_sessions + taf_session_exercises + taf_session_sets)
               - o que voce realmente fez.

A sessao COPIA a prescricao ao iniciar. Editar o plano depois nao reescreve o
historico, e apagar um exercicio nao apaga o que ja foi executado.

Organizador de treino - nao emite prescricao nem orientacao medica.
"""

from __future__ import annotations

import sqlite3

from ..db import execute, insert, query_all, query_one, scalar
from ..utils import now, today_iso

# Categorias sugeridas. E texto livre no banco: acrescentar uma nova categoria
# no futuro nao exige migration.
CATEGORIES = {
    "corrida": "Corrida",
    "caminhada": "Caminhada",
    "forca": "Forca",
    "calistenia": "Calistenia",
    "core": "Core",
    "mobilidade": "Mobilidade",
    "intervalado": "Intervalado",
    "outro": "Outro",
}

WORKOUT_TYPES = dict(CATEGORIES, misto="Misto")

PLAN_STATUS = {"ativo": "Ativo", "arquivado": "Arquivado"}
SESSION_STATUS = {
    "em_andamento": "Em andamento",
    "concluida": "Concluida",
    "abandonada": "Abandonada",
}


# ==========================================================================
# Plano de treino
# ==========================================================================
def create_workout(name: str, **campos) -> int:
    return insert(
        "INSERT INTO taf_workouts (name, objective, type, duration_minutes, start_date,"
        " end_date, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, campos.get("objective", ""), campos.get("type", "forca"),
         campos.get("duration_minutes", 0), campos.get("start_date") or None,
         campos.get("end_date") or None, campos.get("status", "ativo"),
         campos.get("notes", "")),
    )


def update_workout(workout_id: int, name: str, **campos) -> None:
    execute(
        "UPDATE taf_workouts SET name = ?, objective = ?, type = ?, duration_minutes = ?,"
        " start_date = ?, end_date = ?, status = ?, notes = ?,"
        " updated_at = datetime('now') WHERE id = ?",
        (name, campos.get("objective", ""), campos.get("type", "forca"),
         campos.get("duration_minutes", 0), campos.get("start_date") or None,
         campos.get("end_date") or None, campos.get("status", "ativo"),
         campos.get("notes", ""), workout_id),
    )


def get_workout(workout_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM taf_workouts WHERE id = ?", (workout_id,))


def delete_workout(workout_id: int) -> None:
    """Apaga o plano e sua prescricao. As sessoes ja realizadas ficam.

    A FK de taf_workout_sessions.workout_id e ON DELETE SET NULL e o nome do
    treino esta copiado em workout_name, entao o historico continua legivel.
    """
    execute("DELETE FROM taf_workouts WHERE id = ?", (workout_id,))


def list_workouts(status: str | None = "ativo") -> list[dict]:
    sql = [
        "SELECT w.*,"
        " (SELECT COUNT(*) FROM taf_workout_exercises e WHERE e.workout_id = w.id)"
        "   AS exercise_count,"
        " (SELECT COUNT(*) FROM taf_workout_sessions s"
        "   WHERE s.workout_id = w.id AND s.status = 'concluida') AS done_count,"
        " (SELECT MAX(s.date) FROM taf_workout_sessions s"
        "   WHERE s.workout_id = w.id AND s.status = 'concluida') AS last_done"
        " FROM taf_workouts w WHERE 1 = 1"
    ]
    params: list = []
    if status:
        sql.append(" AND w.status = ?")
        params.append(status)
    sql.append(" ORDER BY w.status, w.name")
    return [dict(r) for r in query_all("".join(sql), tuple(params))]


def active_today(reference: str | None = None) -> list[dict]:
    """Planos ativos cuja vigencia inclui a data (vigencia em aberto tambem conta)."""
    day = reference or today_iso()
    return [
        dict(r) for r in query_all(
            "SELECT w.*,"
            " (SELECT COUNT(*) FROM taf_workout_exercises e WHERE e.workout_id = w.id)"
            "   AS exercise_count"
            " FROM taf_workouts w"
            " WHERE w.status = 'ativo'"
            "   AND (w.start_date IS NULL OR w.start_date <= ?)"
            "   AND (w.end_date IS NULL OR w.end_date >= ?)"
            " ORDER BY w.name", (day, day))
    ]


# ==========================================================================
# Exercicios do plano (prescricao)
# ==========================================================================
PRESCRIPTION_FIELDS = ("sets", "reps", "seconds_per_set", "distance_km",
                       "total_seconds", "rest_seconds")


def exercises(workout_id: int) -> list[sqlite3.Row]:
    return query_all(
        "SELECT * FROM taf_workout_exercises WHERE workout_id = ? ORDER BY position, id",
        (workout_id,))


def get_exercise(exercise_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM taf_workout_exercises WHERE id = ?", (exercise_id,))


def next_position(workout_id: int) -> int:
    return int(scalar(
        "SELECT COALESCE(MAX(position), 0) FROM taf_workout_exercises WHERE workout_id = ?",
        (workout_id,), 0)) + 1


def add_exercise(workout_id: int, name: str, **campos) -> int:
    posicao = campos.get("position") or next_position(workout_id)
    return insert(
        "INSERT INTO taf_workout_exercises (workout_id, position, name, category, sets,"
        " reps, seconds_per_set, distance_km, total_seconds, rest_seconds, goal, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (workout_id, posicao, name, campos.get("category", "forca"),
         campos.get("sets"), campos.get("reps"), campos.get("seconds_per_set"),
         campos.get("distance_km"), campos.get("total_seconds"),
         campos.get("rest_seconds"), campos.get("goal", ""), campos.get("notes", "")),
    )


def update_exercise(exercise_id: int, name: str, **campos) -> None:
    execute(
        "UPDATE taf_workout_exercises SET name = ?, category = ?, sets = ?, reps = ?,"
        " seconds_per_set = ?, distance_km = ?, total_seconds = ?, rest_seconds = ?,"
        " goal = ?, notes = ? WHERE id = ?",
        (name, campos.get("category", "forca"), campos.get("sets"), campos.get("reps"),
         campos.get("seconds_per_set"), campos.get("distance_km"),
         campos.get("total_seconds"), campos.get("rest_seconds"),
         campos.get("goal", ""), campos.get("notes", ""), exercise_id),
    )


def delete_exercise(exercise_id: int) -> None:
    row = get_exercise(exercise_id)
    execute("DELETE FROM taf_workout_exercises WHERE id = ?", (exercise_id,))
    if row is not None:
        renumber(row["workout_id"])


def duplicate_exercise(exercise_id: int) -> int | None:
    """Copia um exercicio para o fim da lista - util para variacoes."""
    row = get_exercise(exercise_id)
    if row is None:
        return None
    return insert(
        "INSERT INTO taf_workout_exercises (workout_id, position, name, category, sets,"
        " reps, seconds_per_set, distance_km, total_seconds, rest_seconds, goal, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row["workout_id"], next_position(row["workout_id"]), f"{row['name']} (copia)",
         row["category"], row["sets"], row["reps"], row["seconds_per_set"],
         row["distance_km"], row["total_seconds"], row["rest_seconds"], row["goal"],
         row["notes"]),
    )


def move_exercise(exercise_id: int, direction: int) -> None:
    """Sobe (-1) ou desce (+1) um exercicio, trocando de lugar com o vizinho."""
    row = get_exercise(exercise_id)
    if row is None or direction not in (-1, 1):
        return
    ordenados = exercises(row["workout_id"])
    indices = [e["id"] for e in ordenados]
    if exercise_id not in indices:
        return
    atual = indices.index(exercise_id)
    destino = atual + direction
    if not 0 <= destino < len(indices):
        return
    indices[atual], indices[destino] = indices[destino], indices[atual]
    for posicao, eid in enumerate(indices, start=1):
        execute("UPDATE taf_workout_exercises SET position = ? WHERE id = ?", (posicao, eid))


def renumber(workout_id: int) -> None:
    for posicao, row in enumerate(exercises(workout_id), start=1):
        if row["position"] != posicao:
            execute("UPDATE taf_workout_exercises SET position = ? WHERE id = ?",
                    (posicao, row["id"]))


def describe_prescription(row) -> str:
    """Resumo curto da prescricao, so com os campos preenchidos."""
    partes = []
    if row["sets"]:
        partes.append(f"{row['sets']} serie(s)")
    if row["reps"]:
        partes.append(f"{row['reps']} rep")
    if row["seconds_per_set"]:
        partes.append(f"{row['seconds_per_set']}s por serie")
    if row["distance_km"]:
        partes.append(f"{row['distance_km']:g} km")
    if row["total_seconds"]:
        partes.append(f"{row['total_seconds'] // 60}min no total")
    if row["rest_seconds"]:
        partes.append(f"descanso {row['rest_seconds']}s")
    return " · ".join(partes) or "sem prescricao definida"


# ==========================================================================
# Execucao
# ==========================================================================
def start_session(workout_id: int, date: str | None = None) -> int | None:
    """Cria a sessao copiando a prescricao atual. Sem exercicios, nao inicia."""
    plano = get_workout(workout_id)
    if plano is None:
        return None
    prescricao = exercises(workout_id)
    if not prescricao:
        return None

    session_id = insert(
        "INSERT INTO taf_workout_sessions (workout_id, workout_name, date, started_at,"
        " status) VALUES (?, ?, ?, ?, 'em_andamento')",
        (workout_id, plano["name"], date or today_iso(), now().isoformat(timespec="seconds")),
    )
    for item in prescricao:
        insert(
            "INSERT INTO taf_session_exercises (session_id, workout_exercise_id, position,"
            " name, category, planned_sets, planned_reps, planned_seconds,"
            " planned_distance_km, rest_seconds, goal)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, item["id"], item["position"], item["name"], item["category"],
             item["sets"], item["reps"], item["seconds_per_set"], item["distance_km"],
             item["rest_seconds"], item["goal"]),
        )
    return session_id


def get_session(session_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM taf_workout_sessions WHERE id = ?", (session_id,))


def open_session() -> sqlite3.Row | None:
    """A sessao em andamento, se houver. So faz sentido existir uma por vez."""
    return query_one(
        "SELECT * FROM taf_workout_sessions WHERE status = 'em_andamento'"
        " ORDER BY id DESC LIMIT 1")


def session_exercises(session_id: int) -> list[sqlite3.Row]:
    return query_all(
        "SELECT * FROM taf_session_exercises WHERE session_id = ? ORDER BY position, id",
        (session_id,))


def get_session_exercise(session_exercise_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM taf_session_exercises WHERE id = ?",
                     (session_exercise_id,))


def session_sets(session_exercise_id: int) -> list[sqlite3.Row]:
    return query_all(
        "SELECT * FROM taf_session_sets WHERE session_exercise_id = ? ORDER BY set_number",
        (session_exercise_id,))


def log_set(session_exercise_id: int, **campos) -> int | None:
    """Registra (ou corrige) uma serie realizada."""
    item = query_one("SELECT * FROM taf_session_exercises WHERE id = ?",
                     (session_exercise_id,))
    if item is None:
        return None
    numero = campos.get("set_number") or (len(session_sets(session_exercise_id)) + 1)
    existente = query_one(
        "SELECT id FROM taf_session_sets WHERE session_exercise_id = ? AND set_number = ?",
        (session_exercise_id, numero))
    valores = (campos.get("reps"), campos.get("seconds"), campos.get("distance_km"),
               campos.get("notes", ""))
    if existente:
        execute(
            "UPDATE taf_session_sets SET reps = ?, seconds = ?, distance_km = ?, notes = ?"
            " WHERE id = ?", valores + (existente["id"],))
        return existente["id"]
    return insert(
        "INSERT INTO taf_session_sets (session_exercise_id, set_number, reps, seconds,"
        " distance_km, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (session_exercise_id, numero) + valores)


def delete_set(set_id: int) -> None:
    execute("DELETE FROM taf_session_sets WHERE id = ?", (set_id,))


def set_exercise_status(session_exercise_id: int, status: str) -> None:
    if status in {"pendente", "concluido", "pulado"}:
        execute("UPDATE taf_session_exercises SET status = ? WHERE id = ?",
                (status, session_exercise_id))


def current_exercise(session_id: int) -> sqlite3.Row | None:
    """Primeiro exercicio ainda pendente. None quando todos foram tratados."""
    return query_one(
        "SELECT * FROM taf_session_exercises WHERE session_id = ? AND status = 'pendente'"
        " ORDER BY position, id LIMIT 1", (session_id,))


def finish_session(session_id: int, status: str = "concluida",
                   notes: str | None = None, minutes: int | None = None) -> None:
    if status not in SESSION_STATUS:
        status = "concluida"
    sessao = get_session(session_id)
    if sessao is None:
        return
    duracao = minutes
    if duracao is None:
        duracao = _elapsed_minutes(sessao)
    execute(
        "UPDATE taf_workout_sessions SET status = ?, finished_at = ?, duration_minutes = ?,"
        " notes = COALESCE(?, notes) WHERE id = ?",
        (status, now().isoformat(timespec="seconds"), duracao, notes, session_id))
    # Exercicios nunca tocados nao ficam "pendentes" num treino ja encerrado.
    execute(
        "UPDATE taf_session_exercises SET status = 'pulado'"
        " WHERE session_id = ? AND status = 'pendente'", (session_id,))


def _elapsed_minutes(sessao) -> int:
    from datetime import datetime

    if not sessao["started_at"]:
        return 0
    try:
        inicio = datetime.fromisoformat(sessao["started_at"])
    except ValueError:
        return 0
    agora = now()
    if inicio.tzinfo is None:
        agora = agora.replace(tzinfo=None)
    return max(0, int((agora - inicio).total_seconds() // 60))


def delete_session(session_id: int) -> None:
    execute("DELETE FROM taf_workout_sessions WHERE id = ?", (session_id,))


# ==========================================================================
# Progresso: prescrito x realizado
# ==========================================================================
def exercise_progress(item) -> dict:
    """Compara o prescrito com o realizado para um exercicio da sessao."""
    series = session_sets(item["id"])
    feitas = len(series)
    previstas = item["planned_sets"] or 0

    reps_feitas = sum(s["reps"] or 0 for s in series)
    reps_previstas = (previstas * (item["planned_reps"] or 0)) if item["planned_reps"] else 0
    segundos_feitos = sum(s["seconds"] or 0 for s in series)
    distancia_feita = sum(s["distance_km"] or 0 for s in series)

    if item["planned_reps"]:
        alvo, feito, unidade = reps_previstas, reps_feitas, "rep"
    elif item["planned_distance_km"]:
        alvo = (item["planned_distance_km"] or 0) * max(previstas, 1)
        feito, unidade = distancia_feita, "km"
    elif item["planned_seconds"]:
        alvo = (item["planned_seconds"] or 0) * max(previstas, 1)
        feito, unidade = segundos_feitos, "s"
    else:
        alvo, feito, unidade = previstas, feitas, "serie"

    return {
        "sets": series,
        "sets_done": feitas,
        "sets_planned": previstas,
        "next_set": feitas + 1,
        "reps_done": reps_feitas,
        "reps_planned": reps_previstas,
        "seconds_done": segundos_feitos,
        "distance_done": round(distancia_feita, 2),
        "target": round(alvo, 2) if isinstance(alvo, float) else alvo,
        "achieved": round(feito, 2) if isinstance(feito, float) else feito,
        "unit": unidade,
        "pct": round(feito / alvo * 100, 1) if alvo else None,
    }


def session_summary(session_id: int) -> dict:
    sessao = get_session(session_id)
    if sessao is None:
        return {}
    itens = session_exercises(session_id)
    detalhes = []
    total_series = feitas = 0
    for item in itens:
        progresso = exercise_progress(item)
        total_series += progresso["sets_planned"]
        feitas += progresso["sets_done"]
        detalhes.append({"exercise": item, "progress": progresso})
    return {
        "session": sessao,
        "exercises": detalhes,
        "sets_planned": total_series,
        "sets_done": feitas,
        "pct": round(feitas / total_series * 100, 1) if total_series else None,
        "done_exercises": sum(1 for i in itens if i["status"] == "concluido"),
        "total_exercises": len(itens),
    }


# ==========================================================================
# Historico
# ==========================================================================
def sessions(limit: int = 30, workout_id: int | None = None,
             status: str | None = None) -> list[dict]:
    sql = ["SELECT s.*,"
           " (SELECT COUNT(*) FROM taf_session_exercises e WHERE e.session_id = s.id)"
           "   AS total_exercises,"
           " (SELECT COUNT(*) FROM taf_session_exercises e"
           "   WHERE e.session_id = s.id AND e.status = 'concluido') AS done_exercises"
           " FROM taf_workout_sessions s WHERE 1 = 1"]
    params: list = []
    if workout_id:
        sql.append(" AND s.workout_id = ?")
        params.append(workout_id)
    if status:
        sql.append(" AND s.status = ?")
        params.append(status)
    sql.append(" ORDER BY s.date DESC, s.id DESC LIMIT ?")
    params.append(limit)
    return [dict(r) for r in query_all("".join(sql), tuple(params))]


def minutes_in_period(start: str, end: str) -> int:
    return int(scalar(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM taf_workout_sessions"
        " WHERE status = 'concluida' AND date BETWEEN ? AND ?", (start, end), 0))


def count_in_period(start: str, end: str) -> int:
    return int(scalar(
        "SELECT COUNT(*) FROM taf_workout_sessions"
        " WHERE status = 'concluida' AND date BETWEEN ? AND ?", (start, end), 0))
