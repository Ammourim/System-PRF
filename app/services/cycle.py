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
# Prioridade
# --------------------------------------------------------------------------
# Vocabulario unico do sistema. A ordem deste dicionario E a ordem do ciclo.
PRIORITIES: dict[str, str] = {
    "maxima": "Maxima",
    "alta": "Alta",
    "media": "Media",
    "baixa": "Baixa",
}

PRIORITY_ORDER: dict[str, int] = {key: i for i, key in enumerate(PRIORITIES)}

DEFAULT_PRIORITY = "alta"


def priority_rank(value) -> int:
    """Posicao da prioridade na fila (0 = mais cedo no ciclo)."""
    return PRIORITY_ORDER.get(str(value or DEFAULT_PRIORITY), PRIORITY_ORDER[DEFAULT_PRIORITY])


# --------------------------------------------------------------------------
# Quantidade e tamanho dos blocos
# --------------------------------------------------------------------------
MINUTE_STEP = 5


def split_minutes(total: int, parts: int, step: int = MINUTE_STEP) -> list[int]:
    """Divide `total` minutos em `parts` blocos, em multiplos de `step`.

    Garantia: a soma dos blocos e EXATAMENTE `total`. Nenhum minuto e perdido nem
    inventado - o que sobra da divisao vai para os primeiros blocos.
    """
    total = max(0, int(total))
    parts = int(parts)
    if parts <= 0:
        return []
    if parts == 1:
        return [total]

    base = (total // parts // step) * step
    values = [base] * parts
    rest = total - base * parts
    index = 0
    while rest >= step:
        values[index % parts] += step
        rest -= step
        index += 1
    if rest:
        values[0] += rest
    return values


def blocks_for_target(target_minutes: int, block_minutes: int,
                      min_block_minutes: int = 30, desired_blocks: int = 0,
                      min_blocks: int = 0) -> list[int]:
    """Minutos de cada bloco de uma disciplina. Sem `round()` silencioso.

    A auditoria mostrou que `round(target / block)` distorcia a meta em ate +-33%
    sem avisar (meta 120 com bloco 90 virava 90 min; meta 90 com bloco 60 virava
    120 min). A estrategia aqui e outra:

      1. controle manual vence: `desired_blocks > 0` fixa a quantidade;
      2. senao, usa o teto de `meta / bloco` - assim o bloco nunca fica MAIOR
         que o tamanho preferido pelo usuario;
      3. se isso deixar blocos abaixo de `min_block_minutes`, cai para o piso;
      4. a meta e distribuida entre os blocos escolhidos (multiplos de 5 min),
         somando exatamente a meta.

    Resultado: o erro entre meta e tempo planejado e zero na grande maioria dos
    casos, e quando nao e, `generate_cycle_plan` mostra a diferenca na tela.
    """
    target = max(0, int(target_minutes or 0))
    block = max(MINUTE_STEP, int(block_minutes or 60))
    floor_minutes = max(MINUTE_STEP, int(min_block_minutes or MINUTE_STEP))
    desired = max(0, int(desired_blocks or 0))
    minimum = max(0, int(min_blocks or 0))

    if desired:
        if target <= 0:
            return [block] * desired
        return split_minutes(target, min(desired, max(1, target // MINUTE_STEP)))

    if target <= 0:
        # Sem meta: entra no ciclo apenas se o usuario pediu contato minimo.
        return [block] * minimum

    count = -(-target // block)                     # teto da divisao
    if count > 1 and target / count < floor_minutes:
        count = max(1, target // block)             # piso: blocos curtos demais
    count = max(count, minimum, 1)
    count = min(count, max(1, target // MINUTE_STEP))
    return split_minutes(target, count)


# --------------------------------------------------------------------------
# Distribuicao dos blocos
# --------------------------------------------------------------------------
def spread(items: list[dict]) -> list[dict]:
    """Ordena os blocos do ciclo. A PRIORIDADE manda; o resto so desempata.

    O ciclo e montado em rodadas. Numa rodada, cada disciplina entra no maximo
    uma vez, na ordem: prioridade (maxima > alta > media > baixa), depois
    incidencia historica, depois a ordem recebida. Uma disciplina com k blocos
    entra na rodada `i * rodadas // k`, o que espalha os blocos pelo ciclo sem
    furar a fila de prioridade.

    Assim uma disciplina de prioridade baixa nunca aparece cedo apenas porque tem
    mais blocos - o problema descrito na secao 5.2 da auditoria.

    Aceita `block_list` (minutos de cada bloco) ou o formato antigo
    `count` + `block_minutes`.
    """
    prepared: list[tuple[int, dict, list[int]]] = []
    for order, item in enumerate(items):
        minutes_list = [int(m) for m in (item.get("block_list") or [])]
        if not minutes_list:
            count = int(item.get("count", 0) or 0)
            minutes_list = [int(item.get("block_minutes", 60) or 60)] * max(0, count)
        if not minutes_list:
            continue
        prepared.append((order, item, minutes_list))

    if not prepared:
        return []

    rounds = max(len(minutes) for _, _, minutes in prepared)
    entries: list[tuple[int, int, float, int, int, dict]] = []
    for order, item, minutes_list in prepared:
        total = len(minutes_list)
        rank = priority_rank(item.get("priority"))
        incidence = float(item.get("incidence") or 0)
        for index, minutes in enumerate(minutes_list):
            block = dict(item)
            block.pop("block_list", None)
            block["block_minutes"] = int(minutes)
            entries.append((index * rounds // total, rank, -incidence, order, index, block))

    entries.sort(key=lambda e: e[:5])
    return _separate_neighbours([e[5] for e in entries])


def _rank(block: dict) -> int:
    return priority_rank(block.get("priority"))


def _try_swap(ordered: list[dict], i: int) -> bool:
    """Troca ordered[i] por um bloco adiante, sem criar uma nova repeticao.

    Somente entre blocos de MESMA prioridade: desfazer uma repeticao nunca pode
    custar a ordem de prioridade do ciclo.
    """
    for j in range(i + 1, len(ordered)):
        if _rank(ordered[j]) != _rank(ordered[i]):
            continue
        if ordered[j]["discipline_id"] == ordered[i - 1]["discipline_id"]:
            continue
        before_ok = ordered[j - 1]["discipline_id"] != ordered[i]["discipline_id"] or j == i + 1
        after_ok = (j + 1 >= len(ordered)
                    or ordered[j + 1]["discipline_id"] != ordered[i]["discipline_id"])
        if before_ok and after_ok:
            ordered[i], ordered[j] = ordered[j], ordered[i]
            return True
    return False


def _try_move(ordered: list[dict], i: int) -> bool:
    """Ultimo recurso: reinsere o bloco na primeira posicao sem vizinho igual.

    A posicao tem de continuar dentro da faixa da prioridade do bloco - ele nunca
    passa na frente de uma disciplina mais prioritaria para fugir da repeticao.
    """
    block = ordered.pop(i)
    discipline_id = block["discipline_id"]
    rank = _rank(block)
    for position in range(len(ordered) + 1):
        if position and _rank(ordered[position - 1]) > rank:
            continue
        if position < len(ordered) and _rank(ordered[position]) < rank:
            continue
        before_ok = position == 0 or ordered[position - 1]["discipline_id"] != discipline_id
        after_ok = position == len(ordered) or ordered[position]["discipline_id"] != discipline_id
        if before_ok and after_ok:
            ordered.insert(position, block)
            return True
    ordered.insert(i, block)
    return False


def _separate_neighbours(ordered: list[dict]) -> list[dict]:
    """Evita dois blocos seguidos da mesma disciplina.

    Tenta primeiro uma troca simples; se nao houver troca possivel, reinsere o
    bloco em outra posicao. Se uma disciplina tem mais da metade dos blocos a
    repeticao e inevitavel - nesse caso a funcao reduz o que da e segue em
    frente, sem travar e sem perder blocos.
    """
    for _ in range(3):
        conflicts = [i for i in range(1, len(ordered))
                     if ordered[i]["discipline_id"] == ordered[i - 1]["discipline_id"]]
        if not conflicts:
            break
        for i in conflicts:
            if i >= len(ordered):
                continue
            if ordered[i]["discipline_id"] != ordered[i - 1]["discipline_id"]:
                continue
            if not _try_swap(ordered, i):
                _try_move(ordered, i)
    return ordered


# --------------------------------------------------------------------------
# Planejamento do ciclo (funcao unica e auditavel)
# --------------------------------------------------------------------------
def block_config(conn=None) -> dict:
    """Parametros de bloco/meta vindos de Configuracoes."""
    return {
        "min_block_minutes": settings_service.get_int("cycle_min_block_minutes", 30, conn),
        "tolerance_pct": settings_service.get_float("cycle_goal_tolerance_pct", 5.0, conn),
        "goal_minutes": settings_service.get_int("prf_goal_minutes", 1800, conn),
    }


def _row_value(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def generate_cycle_plan(disciplines, goal_minutes: int | None = None,
                        config: dict | None = None) -> dict:
    """Transforma as disciplinas cadastradas no plano do ciclo, de forma auditavel.

    Passos (na ordem, todos visiveis no resultado):
      1. filtra disciplinas ativas;
      2. le prioridade, meta, bloco, frequencia desejada e contato minimo;
      3. calcula a quantidade e o tamanho dos blocos minimizando o erro contra a
         meta de cada disciplina (`blocks_for_target`);
      4. monta a sequencia respeitando a prioridade (`spread`);
      5. compara o total planejado com a meta do ciclo e devolve os avisos.

    NUNCA reescreve a decisao manual: nem prioridade, nem meta, nem frequencia.
    Divergencia contra a meta e reportada, nao corrigida por conta propria.
    """
    cfg = dict(config or {})
    min_block = int(cfg.get("min_block_minutes", 30))
    tolerance_pct = float(cfg.get("tolerance_pct", 5.0))
    goal = int(goal_minutes if goal_minutes is not None
               else cfg.get("goal_minutes", 1800))

    items: list[dict] = []
    plan: list[dict] = []
    for row in disciplines:
        active = int(_row_value(row, "active", 1) or 0)
        target = int(_row_value(row, "target_minutes", 0) or 0)
        block = max(MINUTE_STEP, int(_row_value(row, "block_minutes", 60) or 60))
        desired = int(_row_value(row, "desired_blocks", 0) or 0)
        minimum = int(_row_value(row, "min_blocks", 0) or 0)
        priority = str(_row_value(row, "priority", DEFAULT_PRIORITY) or DEFAULT_PRIORITY)

        block_list = [] if not active else blocks_for_target(
            target, block, min_block_minutes=min_block,
            desired_blocks=desired, min_blocks=minimum)
        planned = sum(block_list)

        if not active:
            note = "Disciplina inativa - fora do ciclo (continua cadastrada)."
        elif not block_list:
            note = "Meta 0 e sem contato minimo - fora deste ciclo."
        elif desired:
            note = f"Frequencia fixada manualmente em {desired} bloco(s)."
        elif target <= 0 and minimum:
            note = f"Contato minimo de {minimum} bloco(s), sem meta declarada."
        elif planned == target:
            note = "Meta atendida exatamente."
        else:
            note = f"Meta ajustada em {planned - target:+d} min pelo tamanho do bloco."

        item = {
            "discipline_id": _row_value(row, "id"),
            "name": _row_value(row, "name", ""),
            "short_name": _row_value(row, "short_name", ""),
            "priority": priority,
            "priority_rank": priority_rank(priority),
            "priority_label": PRIORITIES.get(priority, priority),
            "status": _row_value(row, "status", ""),
            "incidence": float(_row_value(row, "incidence", 0) or 0),
            "target_minutes": target,
            "block_minutes": block,
            "desired_blocks": desired,
            "min_blocks": minimum,
            "active": bool(active),
            "blocks": len(block_list),
            "block_list": block_list,
            "planned_minutes": planned,
            "diff": planned - target,
            "included": bool(block_list),
            "note": note,
        }
        items.append(item)
        if block_list:
            plan.append(dict(item, count=len(block_list)))

    items.sort(key=lambda i: (i["priority_rank"], -i["incidence"], i["name"]))
    plan.sort(key=lambda i: (i["priority_rank"], -i["incidence"], i["name"]))

    sequence = spread(plan)
    total_minutes = sum(int(b["block_minutes"]) for b in sequence)
    diff = total_minutes - goal
    tolerance = int(round(goal * tolerance_pct / 100))

    warnings: list[str] = []
    if not sequence:
        warnings.append("Nenhuma disciplina com meta ou contato minimo - ciclo vazio.")
    if goal and abs(diff) > tolerance:
        warnings.append(
            f"Total planejado {_hhmm(total_minutes)} contra meta de {_hhmm(goal)}"
            f" ({diff:+d} min). Tolerancia de {tolerance_pct:g}% = +-{tolerance} min.")
    adjusted = [i for i in items if i["included"] and i["diff"]]
    if adjusted:
        warnings.append(
            "Disciplinas com tempo planejado diferente da meta: "
            + ", ".join(f"{i['short_name'] or i['name']} ({i['diff']:+d} min)"
                        for i in adjusted) + ".")

    return {
        "items": items,
        "adjusted": adjusted,
        "plan": plan,
        "sequence": sequence,
        "total_blocks": len(sequence),
        "total_minutes": total_minutes,
        "goal_minutes": goal,
        "diff": diff,
        "tolerance_pct": tolerance_pct,
        "tolerance_minutes": tolerance,
        "within_tolerance": bool(goal) and abs(diff) <= tolerance,
        "warnings": warnings,
    }


def _hhmm(minutes: int) -> str:
    minutes = int(minutes or 0)
    return f"{minutes // 60}h{minutes % 60:02d}"


def plan_from_disciplines(rows, config: dict | None = None) -> list[dict]:
    """Plano pronto para `spread()`/`rebuild_blocks()` a partir das disciplinas.

    Atalho de `generate_cycle_plan` para quem so quer os blocos (seed, scripts).
    """
    return generate_cycle_plan(rows, config=config)["plan"]


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
