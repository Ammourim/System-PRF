"""Exportacao (CSV/JSON) e importacao (CSV) dos dados.

Somente tabelas da lista branca abaixo sao aceitas, e as colunas gravadas sao
validadas contra o schema real (PRAGMA table_info) - nada de nome de tabela ou
coluna vindo direto do formulario para dentro do SQL.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3

from ..db import get_db

EXPORTABLE = [
    "disciplines", "subjects", "study_cycles", "cycle_blocks", "study_sessions",
    "questions", "mistakes", "reviews", "mock_exams", "mock_exam_results",
    "taf_tests", "taf_measurements", "taf_workouts", "college_subjects",
    "college_tasks", "college_sessions", "settings",
]

IMPORTABLE = [
    "disciplines", "subjects", "study_sessions", "questions", "mistakes", "reviews",
    "mock_exams", "taf_tests", "taf_measurements", "taf_workouts",
    "college_subjects", "college_tasks", "college_sessions",
]


def _check(table: str, allowed: list[str]) -> str:
    if table not in allowed:
        raise ValueError(f"Tabela nao permitida: {table}")
    return table


def columns(table: str, conn: sqlite3.Connection | None = None) -> list[str]:
    db = conn or get_db()
    return [r["name"] for r in db.execute(f"PRAGMA table_info({_check(table, EXPORTABLE)})")]


def export_csv(table: str, conn: sqlite3.Connection | None = None) -> str:
    db = conn or get_db()
    table = _check(table, EXPORTABLE)
    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    cols = columns(table, db)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=cols, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row[c] for c in cols})
    return buffer.getvalue()


def export_json(conn: sqlite3.Connection | None = None) -> str:
    db = conn or get_db()
    payload = {
        table: [dict(r) for r in db.execute(f"SELECT * FROM {table}").fetchall()]
        for table in EXPORTABLE
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_csv(table: str, text: str, conn: sqlite3.Connection | None = None) -> dict:
    """Importa linhas de um CSV com cabecalho.

    Colunas desconhecidas sao ignoradas; `id` e descartado para nao sobrescrever
    registros existentes. Retorna {'inserted': n, 'skipped': n, 'errors': [...]}.
    """
    db = conn or get_db()
    table = _check(table, IMPORTABLE)
    valid = set(columns(table, db)) - {"id"}

    reader = csv.DictReader(io.StringIO(text))
    inserted = skipped = 0
    errors: list[str] = []

    for line, raw in enumerate(reader, start=2):
        data = {k.strip(): v for k, v in raw.items() if k and k.strip() in valid}
        data = {k: (None if v == "" else v) for k, v in data.items()}
        if not data:
            skipped += 1
            continue
        cols = list(data)
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        try:
            db.execute(sql, tuple(data[c] for c in cols))
            inserted += 1
        except sqlite3.Error as exc:
            skipped += 1
            if len(errors) < 10:
                errors.append(f"Linha {line}: {exc}")
    db.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}
