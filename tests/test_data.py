"""Testes de persistencia, backup, exportacao/importacao e dados de demo."""

import json

from app.db import backup_database, connect, query_all, restore_database, scalar
from app.seed import clear_demo, has_demo, seed_demo
from app.services import dataio
from app.utils import today_iso

import pytest


def test_migrations_criam_todas_as_tabelas(ctx):
    tables = {r["name"] for r in ctx.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    esperadas = {"disciplines", "subjects", "study_cycles", "cycle_blocks", "study_sessions",
                 "questions", "mistakes", "reviews", "mock_exams", "mock_exam_results",
                 "taf_tests", "taf_workouts", "taf_workout_exercises", "taf_workout_sessions",
                 "taf_session_exercises", "taf_session_sets",
                 "college_subjects", "college_tasks", "settings"}
    assert esperadas.issubset(tables)


def test_dados_base_carregados(ctx):
    assert scalar("SELECT COUNT(*) FROM disciplines", (), 0) == 14
    ctb = ctx.execute("SELECT * FROM disciplines WHERE short_name = 'CTB'").fetchone()
    assert ctb["incidence"] == 25.0
    assert ctb["priority"] == "maxima"
    assert ctb["target_minutes"] == 450   # 5 blocos de 90 min, sem residuo


def test_dados_persistem_entre_conexoes(app):
    with app.app_context():
        from app.db import insert
        insert("INSERT INTO study_sessions (date, type, actual_minutes) VALUES (?, 'teoria', 60)",
               (today_iso(),))
    conn = connect(app.config["DATABASE"])
    try:
        assert conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 1
    finally:
        conn.close()


def test_backup_e_restore(app):
    with app.app_context():
        from app.db import insert
        insert("INSERT INTO study_sessions (date, type, actual_minutes) VALUES (?, 'teoria', 60)",
               (today_iso(),))

    backup_path = backup_database(app)
    assert backup_path.exists() and backup_path.stat().st_size > 0

    with app.app_context():
        from app.db import execute
        execute("DELETE FROM study_sessions")
        assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 0

    restore_database(app, backup_path)
    conn = connect(app.config["DATABASE"])
    try:
        assert conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0] == 1
    finally:
        conn.close()


def test_export_csv_e_json(ctx):
    csv_text = dataio.export_csv("disciplines")
    linhas = csv_text.strip().splitlines()
    assert linhas[0].startswith("id,name,short_name")
    assert len(linhas) == 15  # cabecalho + 14 disciplinas

    payload = json.loads(dataio.export_json())
    assert len(payload["disciplines"]) == 14
    assert "settings" in payload


def test_export_recusa_tabela_desconhecida(ctx):
    with pytest.raises(ValueError):
        dataio.export_csv("sqlite_master")


def test_import_csv(ctx):
    csv_text = (
        "date,discipline_id,total,correct,wrong,percentage,banca\n"
        f"{today_iso()},1,20,15,5,75.0,Cebraspe\n"
        f"{today_iso()},1,10,6,4,60.0,FGV\n"
    )
    result = dataio.import_csv("questions", csv_text)
    assert result["inserted"] == 2 and not result["errors"]
    assert scalar("SELECT SUM(total) FROM questions", (), 0) == 30


def test_import_ignora_coluna_desconhecida_e_id(ctx):
    csv_text = (
        "id,date,discipline_id,total,correct,wrong,percentage,coluna_inventada\n"
        f"999,{today_iso()},1,10,7,3,70.0,lixo\n"
    )
    result = dataio.import_csv("questions", csv_text)
    assert result["inserted"] == 1
    row = query_all("SELECT * FROM questions")[0]
    assert row["id"] != 999


def test_import_recusa_tabela_fora_da_lista(ctx):
    with pytest.raises(ValueError):
        dataio.import_csv("settings", "key,value\nfoo,bar\n")


def test_seed_demo_e_limpeza(ctx):
    assert has_demo(ctx) is False
    seed_demo(ctx)
    assert has_demo(ctx) is True
    assert scalar("SELECT COUNT(*) FROM study_sessions WHERE is_demo = 1", (), 0) > 0
    assert scalar("SELECT COUNT(*) FROM mock_exam_results", (), 0) > 0

    seed_demo(ctx)  # idempotente: nao duplica
    demo_sessions = scalar("SELECT COUNT(*) FROM study_sessions WHERE is_demo = 1", (), 0)

    ctx.execute("INSERT INTO study_sessions (date, type, actual_minutes) VALUES (?, 'teoria', 30)",
                (today_iso(),))
    ctx.commit()

    clear_demo(ctx)
    assert has_demo(ctx) is False
    assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 1  # so o registro real
    assert scalar("SELECT COUNT(*) FROM mock_exam_results", (), 0) == 0
    assert scalar("SELECT COUNT(*) FROM disciplines", (), 0) == 14  # base preservada
    assert demo_sessions > 0
