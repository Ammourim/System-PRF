"""Ciclo de estudos: geracao dos blocos, posicao atual e progresso.

Regra central do sistema: o ciclo NAO depende de calendario. Existe uma posicao
(`study_cycles.current_position`) que so avanca quando o usuario conclui um
bloco. Perder um dia nao cria pendencia, nao reinicia nada e nao pune.
"""

from __future__ import annotations

import sqlite3

from ..db import execute, insert, query_all, query_one, scalar
from ..utils import add_days, today_iso
from . import settings as settings_service


# --------------------------------------------------------------------------
# Distribuicao dos blocos
# --------------------------------------------------------------------------
def spread(items: list[dict]) -> list[dict]:
    """Intercala os blocos para que uma disciplina nao caia toda em sequencia.

    Cada item e um dict com pelo menos {'discipline_id', 'count', ...}. Para uma
    disciplina com k blocos, o i-esimo bloco recebe a chave (i + 0.5) / k, o que
    espalha os blocos uniformemente pelo ciclo. Empates sao resolvidos pela
    disciplina com mais blocos (aparece antes), depois pela ordem informada.

    Como varios empates podem juntar dois blocos da mesma disciplina, um segundo
    passo desfaz repeticoes vizinhas (ver `_separate_neighbours`).
    """
    entries: list[tuple[float, int, int, dict]] = []
    for order, item in enumerate(items):
        count = int(item.get("count", 0))
        if count <= 0:
            continue
        for i in range(count):
            key = (i + 0.5) / count
            entries.append((key, -count, order, item))
    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    return _separate_neighbours([e[3] for e in entries])


def _separate_neighbours(ordered: list[dict]) -> list[dict]:
    """Evita dois blocos seguidos da mesma disciplina, trocando com o vizinho util.

    Se uma disciplina tem mais da metade dos blocos, a repeticao e inevitavel -
    nesse caso a funcao reduz o que da e segue em frente, sem travar.
    """
    for i in range(1, len(ordered)):
        if ordered[i]["discipline_id"] != ordered[i - 1]["discipline_id"]:
            continue
        for j in range(i + 1, len(ordered)):
            candidate = ordered[j]
            if candidate["discipline_id"] == ordered[i - 1]["discipline_id"]:
                continue
            # Nao criar uma nova repeticao no lugar de onde o candidato saiu.
            before_ok = ordered[j - 1]["discipline_id"] != ordered[i]["discipline_id"] or j == i + 1
            after_ok = (j + 1 >= len(ordered)
                        or ordered[j + 1]["discipline_id"] != ordered[i]["discipline_id"])
            if before_ok and after_ok:
                ordered[i], ordered[j] = ordered[j], ordered[i]
                break
    return ordered


def plan_from_disciplines(rows) -> list[dict]:
    """Monta o plano padrao a partir das metas cadastradas nas disciplinas."""
    plan = []
    for row in rows:
        target = int(row["target_minutes"] or 0)
        block = int(row["block_minutes"] or 60) or 60
        if target <= 0:
            continue
        count = max(1, int(target / block + 0.5))
        plan.append(
            {
                "discipline_id": row["id"],
                "name": row["name"],
                "block_minutes": block,
                "target_minutes": target,
                "count": count,
            }
        )
    return plan


# --------------------------------------------------------------------------
# CRUD do ciclo
# --------------------------------------------------------------------------
def active_cycle() -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM study_cycles WHERE status = 'ativo' ORDER BY id DESC LIMIT 1"
    )


def create_cycle(plan: list[dict], start_date: str | None = None, name: str = "",
                 goal_minutes: int | None = None, goal_questions: int | None = None,
                 days: int | None = None, close_active: bool = True) -> int:
    """Cria um ciclo e seus blocos. Encerra o ciclo ativo anterior, se houver."""
    if close_active:
        current = active_cycle()
        if current is not None:
            close_cycle(current["id"])

    days = days or settings_service.get_int("cycle_days", 14)
    start = start_date or today_iso()
    number = int(scalar("SELECT COALESCE(MAX(number), 0) FROM study_cycles", (), 0)) + 1
    cycle_id = insert(
        "INSERT INTO study_cycles (number, name, start_date, end_date, days, goal_minutes,"
        " goal_questions, current_position, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'ativo')",
        (
            number,
            name or f"Ciclo #{number:02d}",
            start,
            add_days(start, days - 1),
            days,
            goal_minutes if goal_minutes is not None
            else settings_service.get_int("prf_goal_minutes", 1800),
            goal_questions if goal_questions is not None
            else settings_service.get_int("questions_goal_per_cycle", 350),
        ),
    )
    rebuild_blocks(cycle_id, plan)
    return cycle_id


def rebuild_blocks(cycle_id: int, plan: list[dict]) -> int:
    """Regera os blocos de um ciclo a partir do plano. Retorna o total de blocos."""
    execute("DELETE FROM cycle_blocks WHERE cycle_id = ?", (cycle_id,))
    ordered = spread(plan)
    for position, item in enumerate(ordered, start=1):
        minutes = int(item.get("block_minutes", 60))
        execute(
            "INSERT INTO cycle_blocks (cycle_id, position, discipline_id, planned_minutes,"
            " block_size) VALUES (?, ?, ?, ?, ?)",
            (
                cycle_id,
                position,
                item["discipline_id"],
                minutes,
                settings_service.block_size_name(minutes),
            ),
        )
    execute("UPDATE study_cycles SET current_position = 1 WHERE id = ?", (cycle_id,))
    return len(ordered)


def blocks(cycle_id: int) -> list[sqlite3.Row]:
    return query_all(
        "SELECT b.*, d.name AS discipline_name, d.short_name, s.name AS subject_name"
        " FROM cycle_blocks b"
        " JOIN disciplines d ON d.id = b.discipline_id"
        " LEFT JOIN subjects s ON s.id = b.subject_id"
        " WHERE b.cycle_id = ? ORDER BY b.position",
        (cycle_id,),
    )


def block_at(cycle_id: int, position: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT b.*, d.name AS discipline_name, d.short_name, d.status AS discipline_status,"
        " s.name AS subject_name"
        " FROM cycle_blocks b"
        " JOIN disciplines d ON d.id = b.discipline_id"
        " LEFT JOIN subjects s ON s.id = b.subject_id"
        " WHERE b.cycle_id = ? AND b.position = ?",
        (cycle_id, position),
    )


def next_block(cycle: sqlite3.Row | None = None) -> sqlite3.Row | None:
    """O bloco da posicao atual. None quando o ciclo terminou ou nao existe."""
    cycle = cycle or active_cycle()
    if cycle is None:
        return None
    return block_at(cycle["id"], cycle["current_position"])


def upcoming(cycle: sqlite3.Row | None = None, limit: int = 5) -> list[sqlite3.Row]:
    cycle = cycle or active_cycle()
    if cycle is None:
        return []
    return query_all(
        "SELECT b.*, d.name AS discipline_name, d.short_name"
        " FROM cycle_blocks b JOIN disciplines d ON d.id = b.discipline_id"
        " WHERE b.cycle_id = ? AND b.position >= ? ORDER BY b.position LIMIT ?",
        (cycle["id"], cycle["current_position"], limit),
    )


def advance(cycle_id: int, block_id: int | None = None, mark_done: bool = True) -> int:
    """Marca o bloco como concluido (opcional) e move a posicao para o proximo.

    Nunca "pula para a data de hoje": apenas incrementa a posicao.
    """
    cycle = query_one("SELECT * FROM study_cycles WHERE id = ?", (cycle_id,))
    if cycle is None:
        return 0
    if mark_done and block_id:
        execute(
            "UPDATE cycle_blocks SET done = 1, done_at = ? WHERE id = ?",
            (today_iso(), block_id),
        )
    total = total_blocks(cycle_id)
    new_position = min(cycle["current_position"] + 1, total + 1)
    execute(
        "UPDATE study_cycles SET current_position = ? WHERE id = ?", (new_position, cycle_id)
    )
    return new_position


def set_position(cycle_id: int, position: int) -> None:
    total = total_blocks(cycle_id)
    position = max(1, min(int(position), max(total, 1) + 1))
    execute("UPDATE study_cycles SET current_position = ? WHERE id = ?", (position, cycle_id))


def toggle_block_done(block_id: int) -> None:
    row = query_one("SELECT done FROM cycle_blocks WHERE id = ?", (block_id,))
    if row is None:
        return
    if row["done"]:
        execute("UPDATE cycle_blocks SET done = 0, done_at = NULL WHERE id = ?", (block_id,))
    else:
        execute(
            "UPDATE cycle_blocks SET done = 1, done_at = ? WHERE id = ?",
            (today_iso(), block_id),
        )


def total_blocks(cycle_id: int) -> int:
    return int(scalar("SELECT COUNT(*) FROM cycle_blocks WHERE cycle_id = ?", (cycle_id,), 0))


def close_cycle(cycle_id: int) -> None:
    execute("UPDATE study_cycles SET status = 'encerrado' WHERE id = ?", (cycle_id,))


def reopen_cycle(cycle_id: int) -> None:
    for row in query_all("SELECT id FROM study_cycles WHERE status = 'ativo'"):
        close_cycle(row["id"])
    execute("UPDATE study_cycles SET status = 'ativo' WHERE id = ?", (cycle_id,))


# --------------------------------------------------------------------------
# Progresso
# --------------------------------------------------------------------------
def progress(cycle: sqlite3.Row | None = None) -> dict:
    """Meta x realizado do ciclo. Nunca esconde a diferenca."""
    cycle = cycle or active_cycle()
    if cycle is None:
        return {"cycle": None}

    cid = cycle["id"]
    total = total_blocks(cid)
    done = int(scalar(
        "SELECT COUNT(*) FROM cycle_blocks WHERE cycle_id = ? AND done = 1", (cid,), 0))
    planned_minutes = int(scalar(
        "SELECT COALESCE(SUM(planned_minutes), 0) FROM cycle_blocks WHERE cycle_id = ?",
        (cid,), 0))

    start, end = cycle["start_date"], cycle["end_date"]
    minutes = int(scalar(
        "SELECT COALESCE(SUM(actual_minutes), 0) FROM study_sessions"
        " WHERE date >= ? AND date <= ?", (start, end), 0))
    questions = int(scalar(
        "SELECT COALESCE(SUM(total), 0) FROM questions WHERE date >= ? AND date <= ?",
        (start, end), 0))
    correct = int(scalar(
        "SELECT COALESCE(SUM(correct), 0) FROM questions WHERE date >= ? AND date <= ?",
        (start, end), 0))

    goal_minutes = int(cycle["goal_minutes"] or 0)
    goal_questions = int(cycle["goal_questions"] or 0)
    return {
        "cycle": cycle,
        "total_blocks": total,
        "done_blocks": done,
        "position": cycle["current_position"],
        "planned_minutes": planned_minutes,
        "minutes": minutes,
        "goal_minutes": goal_minutes,
        "minutes_pct": round(minutes / goal_minutes * 100, 1) if goal_minutes else 0.0,
        "questions": questions,
        "goal_questions": goal_questions,
        "questions_pct": round(questions / goal_questions * 100, 1) if goal_questions else 0.0,
        "correct": correct,
        "accuracy": round(correct / questions * 100, 1) if questions else None,
        "blocks_pct": round(done / total * 100, 1) if total else 0.0,
    }


def estimated_capacity() -> dict:
    """Capacidade bruta declarada em Configuracoes (apenas informativa)."""
    plantoes = settings_service.get_int("plantoes_per_cycle", 7)
    folgas = settings_service.get_int("folgas_per_cycle", 7)
    plantao_h = settings_service.get_float("plantao_hours", 2)
    folga_h = settings_service.get_float("folga_hours", 6)
    total = plantoes * plantao_h + folgas * folga_h
    return {
        "plantoes": plantoes,
        "folgas": folgas,
        "plantao_minutes": int(plantao_h * 60),
        "folga_minutes": int(folga_h * 60),
        "total_minutes": int(total * 60),
    }
