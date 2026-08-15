"""Fabrica da aplicacao Flask do Sistema PRF."""

from __future__ import annotations

from flask import Flask

from . import auth as auth_module
from . import db as db_module
from .config import build_config
from .utils import date_br, fmt_minutes, fmt_num, fmt_pct, performance_level, today_iso

__version__ = "1.0.0"


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.update(build_config())
    if config_overrides:
        app.config.update(config_overrides)

    db_module.init_app(app)

    # Banco pronto no primeiro start: migrations + dados base.
    if not app.config.get("SKIP_AUTO_MIGRATE"):
        conn = db_module.connect(app.config["DATABASE"])
        try:
            from . import seed

            db_module.run_migrations(conn)
            seed.ensure_base_data(conn)
        finally:
            conn.close()

    register_filters(app)
    register_blueprints(app)
    # Depois das blueprints: o guard vale para todas as rotas registradas.
    auth_module.init_app(app)
    register_context(app)
    return app


def register_filters(app: Flask) -> None:
    app.jinja_env.filters["minutes"] = fmt_minutes
    app.jinja_env.filters["pct"] = fmt_pct
    app.jinja_env.filters["num"] = fmt_num
    app.jinja_env.filters["date_br"] = date_br
    app.jinja_env.filters["level"] = performance_level


def register_blueprints(app: Flask) -> None:
    from .blueprints import (
        college,
        cycles,
        dashboard,
        data,
        disciplines,
        mistakes,
        mocks,
        performance,
        questions,
        reviews,
        sessions,
        settings,
        taf,
        workouts,
    )

    for module in (dashboard, cycles, disciplines, sessions, questions, mistakes,
                   reviews, mocks, performance, taf, workouts, college, settings, data):
        app.register_blueprint(module.bp)


def register_context(app: Flask) -> None:
    from flask import request

    from .db import get_db
    from .seed import has_demo
    from .services import reviews as reviews_service

    @app.context_processor
    def inject_globals():
        # As telas de login/bloqueio nao tocam o banco: sem sessao valida, nada
        # de dados do usuario e consultado.
        if request.endpoint in auth_module.PUBLIC_ENDPOINTS:
            return {"app_version": __version__, "auth_enabled": auth_module.enabled()}
        return {
            "today": today_iso(),
            "app_version": __version__,
            "nav_active": request.blueprint,
            "review_badge": reviews_service.counts()["due"],
            "demo_active": has_demo(get_db()),
            "auth_enabled": auth_module.enabled(),
        }
