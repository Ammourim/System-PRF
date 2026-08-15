"""Configuracao da aplicacao.

Le variaveis de ambiente e, se existir, um arquivo .env na raiz do projeto
(parser minimo proprio para nao adicionar dependencia).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEV_SECRET = "dev-local-somente"


def load_dotenv(path: Path | None = None) -> None:
    """Carrega KEY=VALUE de um .env sem sobrescrever variaveis ja definidas.

    Le como utf-8-sig porque o Bloco de Notas e o PowerShell do Windows gravam
    UTF-8 com BOM: sem isso o BOM grudaria no nome da primeira variavel e ela
    seria perdida em silencio.
    """
    path = path or BASE_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_config() -> dict:
    load_dotenv()
    data_dir = BASE_DIR / "data"
    secret = os.environ.get("PRF_SECRET_KEY", DEV_SECRET)
    password_hash = os.environ.get("PRF_PASSWORD_HASH", "").strip()

    # Cookie de sessao assinado com a chave de exemplo seria forjavel - e o login
    # viraria decoracao. Melhor nao subir do que subir inseguro.
    if password_hash and secret == DEV_SECRET:
        raise RuntimeError(
            "PRF_SECRET_KEY ainda e a chave de exemplo. Defina uma chave propria no .env "
            "antes de publicar com senha. Gere uma com:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
        )

    return {
        "SECRET_KEY": secret,
        "PASSWORD_HASH": password_hash,
        "TIMEZONE": os.environ.get("PRF_TIMEZONE", "America/Sao_Paulo"),
        "DATABASE": os.environ.get("PRF_DATABASE", str(data_dir / "prf.db")),
        "BACKUP_DIR": os.environ.get("PRF_BACKUP_DIR", str(BASE_DIR / "backups")),
        "EXPORT_DIR": os.environ.get("PRF_EXPORT_DIR", str(BASE_DIR / "exports")),
        "HOST": os.environ.get("PRF_HOST", "127.0.0.1"),
        "PORT": int(os.environ.get("PRF_PORT", "5000")),
        "DEBUG": os.environ.get("PRF_DEBUG", "0") == "1",
        "MAX_CONTENT_LENGTH": 8 * 1024 * 1024,  # limite de upload (import CSV)
        # Sessao: longa de proposito, para nao pedir senha toda hora no celular.
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": os.environ.get("PRF_HTTPS", "0") == "1",
    }
