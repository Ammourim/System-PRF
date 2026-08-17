"""Configuracoes do sistema (tabela `settings`).

Toda meta, intervalo e tamanho de bloco vive aqui - nada fica hardcoded no
codigo alem dos valores PADRAO, usados apenas quando a chave nunca foi gravada.
"""

from __future__ import annotations

import sqlite3

from ..db import get_db

DEFAULTS: dict[str, str] = {
    # Ciclo
    "cycle_days": "14",
    "prf_goal_minutes": "1800",          # 30h por ciclo de 14 dias
    "questions_goal_per_cycle": "350",
    "questions_goal_per_folga": "50",
    # Montagem do ciclo
    "cycle_goal_tolerance_pct": "5",     # divergencia aceita contra prf_goal_minutes
    "cycle_min_block_minutes": "30",     # piso ao dividir a meta em blocos
    # Tamanhos de bloco (minutos)
    "block_long": "90",
    "block_medium": "60",
    "block_short": "45",
    # Disponibilidade declarada (usada apenas para exibir a capacidade estimada)
    "plantao_hours": "2",
    "folga_hours": "6",
    "plantoes_per_cycle": "7",
    "folgas_per_cycle": "7",
    # Objetivos do dia (o ciclo simplificado)
    "today_max_disciplines": "5",        # teto de disciplinas por dia (0 = sem teto)
    # Revisao espacada
    "review_intervals": "1,7,15,30,60",
    # Simulados
    "mock_frequency": "quinzenal",       # semanal|quinzenal|mensal|manual
    "mock_default_minutes": "300",
    "mock_default_questions": "120",
    "mock_snooze_until": "",             # silencia o aviso do painel ate esta data
    # TAF e faculdade
    "taf_minutes_per_cycle": "420",      # ~7h
    "college_hours_per_week": "4",
    # Limiares de desempenho (usados nas cores e nas sugestoes)
    "performance_low": "60",
    "performance_mid": "70",
    # Distribuicao sugerida de questoes (novo + revisao)
    "questions_split_new": "30",
    "questions_split_review": "20",
}


def all_settings(conn: sqlite3.Connection | None = None) -> dict[str, str]:
    db = conn or get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    values = dict(DEFAULTS)
    values.update({r["key"]: r["value"] for r in rows})
    return values


def get(key: str, default: str | None = None, conn: sqlite3.Connection | None = None) -> str:
    db = conn or get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["value"]
    return DEFAULTS.get(key, default if default is not None else "")


def get_int(key: str, default: int = 0, conn: sqlite3.Connection | None = None) -> int:
    try:
        return int(float(get(key, str(default), conn)))
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0, conn: sqlite3.Connection | None = None) -> float:
    try:
        return float(str(get(key, str(default), conn)).replace(",", "."))
    except (TypeError, ValueError):
        return default


def get_list_int(key: str, conn: sqlite3.Connection | None = None) -> list[int]:
    raw = get(key, DEFAULTS.get(key, ""), conn)
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(float(part)))
        except ValueError:
            continue
    return out


def set_value(key: str, value, conn: sqlite3.Connection | None = None) -> None:
    db = conn or get_db()
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, str(value)),
    )
    db.commit()


def set_many(values: dict[str, object], conn: sqlite3.Connection | None = None) -> None:
    db = conn or get_db()
    for key, value in values.items():
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
            (key, str(value)),
        )
    db.commit()


def block_sizes(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    return {
        "longo": get_int("block_long", 90, conn),
        "medio": get_int("block_medium", 60, conn),
        "curto": get_int("block_short", 45, conn),
    }


def block_size_name(minutes: int, conn: sqlite3.Connection | None = None) -> str:
    for name, value in block_sizes(conn).items():
        if value == minutes:
            return name
    return "custom"
