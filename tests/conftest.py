"""Fixtures dos testes: app com banco SQLite temporario e isolado."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "DATABASE": str(tmp_path / "test.db"),
        "BACKUP_DIR": str(tmp_path / "backups"),
        "EXPORT_DIR": str(tmp_path / "exports"),
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
    })
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def ctx(app):
    """Contexto de aplicacao ativo - permite usar get_db()/servicos direto."""
    with app.app_context():
        yield get_db()
