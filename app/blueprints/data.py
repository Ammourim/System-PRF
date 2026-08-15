"""Backup, exportacao (CSV/JSON) e importacao (CSV)."""

from __future__ import annotations

from pathlib import Path

from flask import (Blueprint, Response, current_app, flash, redirect, render_template,
                   request, send_file, url_for)

from ..db import backup_database, restore_database
from ..services import dataio
from ..utils import today_iso

bp = Blueprint("data", __name__, url_prefix="/dados")


def _backups() -> list[dict]:
    directory = Path(current_app.config["BACKUP_DIR"])
    if not directory.exists():
        return []
    files = sorted(directory.glob("prf-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1),
         "modified": p.stat().st_mtime}
        for p in files[:20]
    ]


@bp.route("/")
def index():
    return render_template(
        "data/index.html",
        tables=dataio.EXPORTABLE,
        importable=dataio.IMPORTABLE,
        backups=_backups(),
        database=current_app.config["DATABASE"],
        backup_dir=current_app.config["BACKUP_DIR"],
    )


@bp.route("/exportar/<table>.csv")
def export_csv(table: str):
    try:
        content = dataio.export_csv(table)
    except ValueError:
        flash("Tabela invalida.", "error")
        return redirect(url_for("data.index"))
    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="{table}-{today_iso()}.csv"'},
    )


@bp.route("/exportar.json")
def export_json():
    return Response(
        dataio.export_json(),
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="prf-backup-{today_iso()}.json"'},
    )


@bp.route("/importar", methods=["POST"])
def import_csv():
    table = request.form.get("table", "")
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Selecione um arquivo CSV.", "error")
        return redirect(url_for("data.index"))
    try:
        raw = upload.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        result = dataio.import_csv(table, text)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("data.index"))

    message = f"{result['inserted']} linha(s) importada(s), {result['skipped']} ignorada(s)."
    if result["errors"]:
        message += " Erros: " + " | ".join(result["errors"])
        flash(message, "error")
    else:
        flash(message, "success")
    return redirect(url_for("data.index"))


@bp.route("/backup", methods=["POST"])
def backup():
    target = backup_database(current_app)
    flash(f"Backup criado: {target.name}", "success")
    return redirect(url_for("data.index"))


@bp.route("/backup/<name>")
def download_backup(name: str):
    path = (Path(current_app.config["BACKUP_DIR"]) / name).resolve()
    root = Path(current_app.config["BACKUP_DIR"]).resolve()
    if root not in path.parents or not path.exists():
        flash("Backup nao encontrado.", "error")
        return redirect(url_for("data.index"))
    return send_file(path, as_attachment=True)


@bp.route("/backup/restaurar", methods=["POST"])
def restore():
    name = request.form.get("name", "")
    path = (Path(current_app.config["BACKUP_DIR"]) / name).resolve()
    root = Path(current_app.config["BACKUP_DIR"]).resolve()
    if root not in path.parents or not path.exists():
        flash("Backup nao encontrado.", "error")
        return redirect(url_for("data.index"))
    restore_database(current_app, path)
    flash(f"Backup {name} restaurado. Reinicie o servidor para garantir a leitura limpa.",
          "success")
    return redirect(url_for("data.index"))
