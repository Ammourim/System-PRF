"""Acesso ao banco SQLite e execucao de migrations.

Sem ORM de proposito: o projeto e pessoal, o SQL fica visivel e as migrations
sao arquivos .sql numerados aplicados em ordem e registrados em `schema_migrations`.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import click
from flask import current_app, g

from .utils import now

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db() -> sqlite3.Connection:
    """Conexao da requisicao atual (criada sob demanda)."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def connect(path: str | Path) -> sqlite3.Connection:
    """Abre uma conexao configurada (usada tambem por testes e scripts)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def close_db(_exception=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------
# Helpers de consulta
# --------------------------------------------------------------------------
def query_all(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def scalar(sql: str, params: tuple | dict = (), default=None):
    row = query_one(sql, params)
    if row is None or row[0] is None:
        return default
    return row[0]


def execute(sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def insert(sql: str, params: tuple | dict = ()) -> int:
    return int(execute(sql, params).lastrowid)


# --------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------
def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()
    return {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Aplica migrations pendentes em ordem alfabetica. Retorna as aplicadas."""
    done = applied_migrations(conn)
    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (path.name,))
        conn.commit()
        applied.append(path.name)
    return applied


def backup_database(app, destination_dir: str | Path | None = None) -> Path:
    """Copia consistente do SQLite (usa a API de backup, segura com WAL)."""
    dest_dir = Path(destination_dir or app.config["BACKUP_DIR"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    target = dest_dir / f"prf-{stamp}.db"

    source = connect(app.config["DATABASE"])
    try:
        dest = sqlite3.connect(str(target))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


def restore_database(app, backup_path: str | Path) -> Path:
    """Restaura um backup por cima do banco atual (guarda o anterior antes)."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    current = Path(app.config["DATABASE"])
    if current.exists():
        safety = current.with_name(
            f"{current.stem}-antes-restore-{now():%Y%m%d-%H%M%S}.db"
        )
        shutil.copy2(current, safety)
    shutil.copy2(backup_path, current)
    return current


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(backup_command)
    app.cli.add_command(set_password_command)


@click.command("init-db")
def init_db_command():
    """Cria/atualiza o banco e grava os dados iniciais (disciplinas, settings)."""
    from . import seed

    conn = connect(current_app.config["DATABASE"])
    try:
        applied = run_migrations(conn)
        seed.ensure_base_data(conn)
        conn.commit()
    finally:
        conn.close()
    click.echo(f"Banco pronto. Migrations aplicadas: {applied or 'nenhuma (ja estava atualizado)'}")


@click.command("seed-demo")
def seed_demo_command():
    """Insere dados de demonstracao (marcados como demo, removiveis)."""
    from . import seed

    conn = connect(current_app.config["DATABASE"])
    try:
        run_migrations(conn)
        seed.ensure_base_data(conn)
        seed.seed_demo(conn)
        conn.commit()
    finally:
        conn.close()
    click.echo("Dados de demonstracao inseridos.")


@click.command("backup")
def backup_command():
    """Gera um backup do banco em backups/."""
    target = backup_database(current_app)
    click.echo(f"Backup criado: {target}")


@click.command("set-password")
def set_password_command():
    """Gera o hash da senha de acesso para colar no .env.

    A senha em texto puro nunca e gravada em lugar nenhum.
    """
    import secrets

    from .auth import make_hash

    password = click.prompt("Nova senha", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        click.echo("Use pelo menos 8 caracteres.")
        raise SystemExit(1)

    click.echo("\nCopie as linhas abaixo para o arquivo .env:\n")
    click.echo(f"PRF_PASSWORD_HASH={make_hash(password)}")
    if current_app.config.get("SECRET_KEY") == "dev-local-somente":
        click.echo(f"PRF_SECRET_KEY={secrets.token_hex(32)}")
    click.echo("\nDepois recarregue a aplicacao.")
