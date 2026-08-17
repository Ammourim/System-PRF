"""Assunto: o que voce esta estudando e quando ele TERMINA.

Distincao fundamental do sistema:

  registrar estudo  != assunto concluido

Estudar "Infracoes de transito" segunda, terca e quarta gera tres registros e o
assunto continua EM ANDAMENTO. Ele so termina quando o usuario declara
"terminei este assunto" - e e esse momento que da inicio a revisao espacada.

O assunto e texto livre: digitar o nome cria o assunto na hora, sem cadastro
previo de arvore de conteudo.
"""

from __future__ import annotations

import sqlite3

from ..db import execute, insert, query_one
from ..utils import as_text, today_iso

STATUS = {
    "nao_iniciada": "Nao iniciado",
    "em_andamento": "Em andamento",
    "concluida": "Concluido",
}


def resolve(discipline_id: int | None, name, subject_id=None) -> int | None:
    """Assunto existente (por id ou por nome) ou criado agora. Sem duplicar."""
    if subject_id:
        return int(subject_id)
    text = as_text(name, max_length=120)
    if not text or not discipline_id:
        return None
    existing = query_one(
        "SELECT id FROM subjects WHERE discipline_id = ? AND lower(name) = lower(?)",
        (discipline_id, text))
    if existing:
        return existing["id"]
    return insert(
        "INSERT INTO subjects (discipline_id, name, status) VALUES (?, ?, 'em_andamento')",
        (discipline_id, text))


def mark_in_progress(subject_id: int | None) -> None:
    """Registrar estudo nunca conclui o assunto - no maximo o reabre."""
    if not subject_id:
        return
    execute(
        "UPDATE subjects SET status = 'em_andamento' WHERE id = ? AND status = 'nao_iniciada'",
        (subject_id,))


def complete(subject_id: int, date: str | None = None) -> sqlite3.Row | None:
    """Marca o assunto como concluido na data real informada."""
    row = query_one(
        "SELECT s.*, d.name AS discipline_name, d.short_name FROM subjects s"
        " JOIN disciplines d ON d.id = s.discipline_id WHERE s.id = ?", (subject_id,))
    if row is None:
        return None
    execute("UPDATE subjects SET status = 'concluida', completed_at = ? WHERE id = ?",
            (date or today_iso(), subject_id))
    return row


def reopen(subject_id: int) -> None:
    """Voltar atras: o assunto nao estava terminado. Nao mexe nas revisoes."""
    execute("UPDATE subjects SET status = 'em_andamento', completed_at = NULL WHERE id = ?",
            (subject_id,))
