"""Helpers compartilhados pelas blueprints."""

from __future__ import annotations

from flask import request

from ..db import insert, query_all, query_one
from ..services.cycle import DEFAULT_PRIORITY, PRIORITIES, PRIORITY_ORDER  # noqa: F401
from ..utils import as_opt_int, as_text

SESSION_TYPES = {
    "teoria": "Teoria",
    "questoes": "Questoes",
    "revisao": "Revisao",
    "simulado": "Simulado",
    "correcao_simulado": "Correcao de simulado",
    "redacao": "Redacao",
    "outro": "Outro",
}

MISTAKE_CATEGORIES = {
    "C": "Nao conhecia o conteudo",
    "E": "Esqueci",
    "I": "Interpretacao",
    "A": "Atencao",
    "D": "Duvida entre alternativas",
    "CH": "Chute",
}

DISCIPLINE_STATUS = {
    "nao_iniciada": "Nao iniciada",
    "em_andamento": "Em andamento",
    "revisao": "Revisao",
    "consolidada": "Consolidada",
}

# PRIORITIES / PRIORITY_ORDER vivem em services/cycle.py: prioridade agora e uma
# regra do ciclo, nao apenas um rotulo de tela.

# Ordena por prioridade antes de qualquer outra coisa (mesma regra do ciclo).
_PRIORITY_SQL = ("CASE d.priority " +
                 " ".join(f"WHEN '{key}' THEN {rank}"
                          for key, rank in PRIORITY_ORDER.items()) +
                 f" ELSE {PRIORITY_ORDER[DEFAULT_PRIORITY]} END")


def priority_sql(alias: str = "d") -> str:
    """Expressao SQL que ordena pela prioridade do ciclo."""
    return _PRIORITY_SQL.replace("d.priority", f"{alias}.priority")


def disciplines(active_only: bool = True) -> list:
    sql = "SELECT * FROM disciplines d"
    if active_only:
        sql += " WHERE active = 1"
    sql += f" ORDER BY {priority_sql()}, incidence DESC, name"
    return query_all(sql)


def subjects(discipline_id: int | None = None) -> list:
    if discipline_id:
        return query_all(
            "SELECT * FROM subjects WHERE discipline_id = ? ORDER BY name", (discipline_id,))
    return query_all(
        "SELECT s.*, d.short_name FROM subjects s JOIN disciplines d ON d.id = s.discipline_id"
        " ORDER BY d.incidence DESC, s.name")


def resolve_subject(discipline_id: int | None, subject_id_value, subject_name_value) -> int | None:
    """Aceita um assunto existente OU um nome digitado (cria na hora).

    Digitar o assunto direto no formulario evita a ida-e-volta de cadastrar
    antes de registrar a sessao (regra 51: menos cliques).
    """
    subject_id = as_opt_int(subject_id_value)
    if subject_id:
        return subject_id
    name = as_text(subject_name_value, max_length=120)
    if not name or not discipline_id:
        return None
    existing = query_one(
        "SELECT id FROM subjects WHERE discipline_id = ? AND lower(name) = lower(?)",
        (discipline_id, name))
    if existing:
        return existing["id"]
    return insert(
        "INSERT INTO subjects (discipline_id, name, status) VALUES (?, ?, 'em_andamento')",
        (discipline_id, name))


def form_subject(discipline_id: int | None) -> int | None:
    return resolve_subject(
        discipline_id, request.form.get("subject_id"), request.form.get("subject_name"))


def redirect_target(default: str) -> str:
    """Volta para a tela de origem quando informada (campo oculto `next`)."""
    target = request.form.get("next") or request.args.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return default
