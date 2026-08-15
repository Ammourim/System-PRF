"""A migration 002 converte treinos do formato antigo sem perder dados.

Os demais testes rodam sobre bancos vazios, entao as consultas de conversao
nunca seriam exercitadas. Aqui montamos um banco no estado da migration 001,
com linhas reais, e so entao aplicamos a 002.
"""

import sqlite3

import pytest

from app.db import MIGRATIONS_DIR, connect, run_migrations


@pytest.fixture()
def banco_antigo(tmp_path):
    """Banco no estado da migration 001, com treinos no formato antigo."""
    caminho = tmp_path / "antigo.db"
    conn = connect(caminho)
    conn.executescript((MIGRATIONS_DIR / "001_initial.sql").read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.execute("INSERT INTO schema_migrations (name) VALUES ('001_initial.sql')")

    linhas = [
        # data, nome, tipo, duracao, exercicio, series, reps, distancia, tempo, status
        ("2026-08-01", "Treino A - Corrida", "corrida", 50, "Intervalado 6x400m",
         None, None, 6.0, "", "concluido"),
        ("2026-08-03", "Treino B - Forca", "forca", 45, "Barra + flexao", 4, 8, None,
         "", "concluido"),
        ("2026-08-05", "Treino B - Forca", "forca", 45, "Circuito", 4, 10, None,
         "12:00", "pendente"),
        ("2026-08-07", "", "misto", 30, "", None, None, None, "", "planejado"),
    ]
    for linha in linhas:
        conn.execute(
            "INSERT INTO taf_workouts (date, name, type, duration_minutes, exercise, sets,"
            " reps, distance_km, time_text, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            linha)
    conn.commit()
    return conn


def test_migration_preserva_todos_os_treinos(banco_antigo):
    run_migrations(banco_antigo)
    planos = banco_antigo.execute(
        "SELECT * FROM taf_workouts ORDER BY id").fetchall()
    assert len(planos) == 4
    assert [p["name"] for p in planos][:2] == ["Treino A - Corrida", "Treino B - Forca"]


def test_data_antiga_vira_vigencia(banco_antigo):
    run_migrations(banco_antigo)
    plano = banco_antigo.execute(
        "SELECT * FROM taf_workouts WHERE name = 'Treino A - Corrida'").fetchone()
    assert plano["start_date"] == "2026-08-01"
    assert plano["end_date"] == "2026-08-01"
    assert plano["status"] == "ativo"


def test_treino_sem_nome_ganha_um(banco_antigo):
    run_migrations(banco_antigo)
    nomes = [p["name"] for p in banco_antigo.execute("SELECT name FROM taf_workouts")]
    assert "" not in nomes
    assert any(n.startswith("Treino ") for n in nomes)


def test_campos_soltos_viram_exercicio(banco_antigo):
    run_migrations(banco_antigo)
    exercicios = banco_antigo.execute(
        "SELECT * FROM taf_workout_exercises ORDER BY id").fetchall()
    # A quarta linha nao tinha exercicio nem prescricao: nao gera exercicio vazio.
    assert len(exercicios) == 3

    corrida = exercicios[0]
    assert corrida["name"] == "Intervalado 6x400m"
    assert corrida["distance_km"] == 6.0
    assert corrida["position"] == 1

    forca = exercicios[1]
    assert forca["sets"] == 4 and forca["reps"] == 8

    # time_text nao tinha campo equivalente: vira meta, em vez de ser descartado.
    circuito = exercicios[2]
    assert circuito["goal"] == "12:00"


def test_treinos_concluidos_viram_sessoes(banco_antigo):
    run_migrations(banco_antigo)
    sessoes = banco_antigo.execute(
        "SELECT * FROM taf_workout_sessions ORDER BY date").fetchall()
    assert len(sessoes) == 2  # so os que estavam 'concluido'
    assert sessoes[0]["date"] == "2026-08-01"
    assert sessoes[0]["status"] == "concluida"
    assert sessoes[0]["duration_minutes"] == 50
    assert sessoes[0]["workout_name"] == "Treino A - Corrida"


def test_tabela_antiga_e_removida(banco_antigo):
    run_migrations(banco_antigo)
    tabelas = {r["name"] for r in banco_antigo.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "taf_workouts_legacy" not in tabelas
    assert {"taf_workout_exercises", "taf_workout_sessions",
            "taf_session_exercises", "taf_session_sets"} <= tabelas


def test_migration_e_idempotente(banco_antigo):
    """Rodar de novo nao duplica nada - a 002 ja consta em schema_migrations."""
    run_migrations(banco_antigo)
    antes = banco_antigo.execute("SELECT COUNT(*) FROM taf_workouts").fetchone()[0]
    aplicadas = run_migrations(banco_antigo)
    assert aplicadas == []
    assert banco_antigo.execute("SELECT COUNT(*) FROM taf_workouts").fetchone()[0] == antes


def test_integridade_do_banco_apos_migration(banco_antigo):
    run_migrations(banco_antigo)
    assert banco_antigo.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert banco_antigo.execute("PRAGMA foreign_key_check").fetchall() == []


def test_aplicacao_sobe_sobre_o_banco_migrado(tmp_path, banco_antigo):
    """Depois da migration o app inicia e as telas de treino respondem."""
    from app import create_app

    caminho = banco_antigo.execute("PRAGMA database_list").fetchone()["file"]
    banco_antigo.commit()
    banco_antigo.close()

    app = create_app({"DATABASE": caminho, "BACKUP_DIR": str(tmp_path / "b"),
                      "TESTING": True, "SECRET_KEY": "t"})
    client = app.test_client()
    assert client.get("/taf/treinos/").status_code == 200
    assert client.get("/taf/").status_code == 200

    conn = sqlite3.connect(caminho)
    try:
        assert conn.execute("SELECT COUNT(*) FROM taf_workouts").fetchone()[0] == 4
    finally:
        conn.close()
