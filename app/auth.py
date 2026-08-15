"""Autenticacao de usuario unico e protecao contra CSRF.

Desenho a prova de falha: se a aplicacao for publicada SEM senha configurada,
ela se recusa a responder para hosts externos, em vez de ficar aberta. Rodando
em localhost sem senha, o comportamento e o de sempre - uso local sem atrito.

A senha vive como hash em PRF_PASSWORD_HASH (arquivo .env), nunca no banco:
assim ela nao vaza nos backups nem nas exportacoes de /dados/.
"""

from __future__ import annotations

from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .utils import now

bp = Blueprint("auth", __name__)

# Endpoints acessiveis sem sessao.
PUBLIC_ENDPOINTS = {"auth.login", "auth.health", "static"}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}

MAX_ATTEMPTS = 5
BLOCK_MINUTES = 15

# {ip: (falhas, bloqueado_ate)}. Em memoria de proposito: o plano gratuito roda
# um unico worker, e reiniciar zerar o contador e aceitavel para uso pessoal.
_attempts: dict[str, tuple[int, float]] = {}


# --------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------
def password_hash() -> str:
    return current_app.config.get("PASSWORD_HASH", "") or ""


def enabled() -> bool:
    """A autenticacao esta configurada?"""
    return bool(password_hash())


def is_local_host() -> bool:
    host = (request.host or "").split(":")[0].lower()
    return host in LOCAL_HOSTS


def logged_in() -> bool:
    return bool(session.get("auth"))


def make_hash(password: str) -> str:
    return generate_password_hash(password)


# --------------------------------------------------------------------------
# Forca bruta
# --------------------------------------------------------------------------
def _client_ip() -> str:
    return request.remote_addr or "desconhecido"


def blocked_for() -> int:
    """Minutos restantes de bloqueio do IP atual (0 = liberado)."""
    failures, until = _attempts.get(_client_ip(), (0, 0.0))
    if failures < MAX_ATTEMPTS:
        return 0
    remaining = until - now().timestamp()
    if remaining <= 0:
        _attempts.pop(_client_ip(), None)
        return 0
    return max(1, int(remaining // 60) + 1)


def register_failure() -> None:
    ip = _client_ip()
    failures = _attempts.get(ip, (0, 0.0))[0] + 1
    _attempts[ip] = (failures, now().timestamp() + BLOCK_MINUTES * 60)


def clear_failures() -> None:
    _attempts.pop(_client_ip(), None)


# --------------------------------------------------------------------------
# Guarda global
# --------------------------------------------------------------------------
def _csrf_ok() -> bool:
    """Confere se um POST veio da propria aplicacao.

    Navegadores sempre enviam Origin em POST cross-site; ausencia de Origin e
    Referer indica cliente nao-navegador (curl, testes). Junto do cookie
    SameSite=Lax, cobre o caso real sem exigir um token em cada formulario.
    """
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return True

    origin = request.headers.get("Origin")
    source = origin or request.headers.get("Referer")
    if not source:
        return True

    from urllib.parse import urlsplit

    return urlsplit(source).netloc == request.host


def init_app(app) -> None:
    app.register_blueprint(bp)

    @app.before_request
    def _guard():
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None

        if not _csrf_ok():
            return render_template("auth/blocked.html", reason="csrf"), 400

        if not enabled():
            if is_local_host():
                return None  # uso local de sempre
            # Publicado sem senha: recusar em vez de servir dados abertos.
            return render_template("auth/blocked.html", reason="sem_senha"), 503

        if logged_in():
            return None
        return redirect(url_for("auth.login", next=request.full_path))


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------
@bp.route("/saude")
def health():
    """Checagem simples de que a aplicacao subiu (nao expoe dado algum)."""
    return {"ok": True}


@bp.route("/entrar", methods=["GET", "POST"])
def login():
    if not enabled():
        return redirect(url_for("dashboard.index"))
    if logged_in():
        return redirect(url_for("dashboard.index"))

    blocked = blocked_for()
    if request.method == "POST":
        if blocked:
            flash(f"Muitas tentativas. Tente novamente em {blocked} minuto(s).", "error")
        elif check_password_hash(password_hash(), request.form.get("password", "")):
            clear_failures()
            session.clear()
            session["auth"] = True
            session.permanent = True
            destination = request.form.get("next") or request.args.get("next") or ""
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("dashboard.index"))
        else:
            register_failure()
            flash("Senha incorreta.", "error")
        blocked = blocked_for()

    return render_template("auth/login.html", blocked=blocked)


@bp.route("/sair", methods=["POST"])
def logout():
    session.clear()
    flash("Sessao encerrada.", "success")
    return redirect(url_for("auth.login"))
