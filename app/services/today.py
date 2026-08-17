"""O nucleo do sistema simplificado: o que estudar HOJE.

Este modulo responde uma unica pergunta - "quais disciplinas aparecem como
objetivo hoje?" - e responde de forma que o usuario consiga conferir de cabeca.

Regras, todas explicitas:
  * cada disciplina ativa tem uma FREQUENCIA: quantos dias por semana ela
    aparece (1 a 7). Prioridade so define o valor PADRAO da frequencia e a
    ordem de exibicao;
  * a escolha do dia e deterministica: a mesma data sempre gera a mesma lista.
    Abrir a tela dez vezes nao muda nada e nao grava nada;
  * nao existe agenda, tarefa ou pendencia. Nao estudar hoje nao acumula nada:
    amanha o dia e calculado de novo, do zero.

NAO ha minutos, blocos, metas nem distribuicao matematica aqui. O ciclo antigo
(services/cycle.py) continua existindo para quem quiser o detalhe, mas nao
participa do dia a dia.
"""

from __future__ import annotations

from ..db import query_all, query_one, scalar
from ..utils import parse_date, today_iso
from . import settings as settings_service
from .cycle import PRIORITIES, priority_rank  # noqa: F401  (vocabulario unico)

WEEK = 7

# Frequencia padrao por prioridade (dias por semana). Editavel por disciplina.
PRIORITY_FREQUENCY: dict[str, int] = {
    "maxima": 5,
    "alta": 3,
    "media": 2,
    "baixa": 1,
}
DEFAULT_FREQUENCY = 2

# Texto usado na interface - a regra tem de ser explicada onde e editada.
FREQUENCY_LABELS: dict[int, str] = {
    1: "1x por semana",
    2: "2x por semana",
    3: "3x por semana",
    4: "4x por semana",
    5: "5x por semana",
    6: "6x por semana",
    7: "todos os dias",
}


def default_frequency(priority) -> int:
    return PRIORITY_FREQUENCY.get(str(priority or ""), DEFAULT_FREQUENCY)


def frequency_of(row) -> int:
    """Frequencia efetiva da disciplina (1 a 7). 0 = deduzir da prioridade."""
    try:
        value = int(row["frequency"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        value = 0
    if value <= 0:
        value = default_frequency(_get(row, "priority"))
    return max(1, min(WEEK, value))


def frequency_label(value: int) -> str:
    return FREQUENCY_LABELS.get(max(1, min(WEEK, int(value or 1))), "")


def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def lands_on(day_number: int, frequency: int, offset: int = 0) -> bool:
    """A disciplina cai neste dia?

    Sequencia de Bresenham sobre a semana: com frequencia f, exatamente f de
    cada 7 dias consecutivos dao verdadeiro, e os dias ficam espalhados (nunca
    todos colados no inicio da semana). O `offset` (id da disciplina) evita que
    todas as disciplinas caiam no mesmo dia.
    """
    frequency = max(1, min(WEEK, int(frequency or 1)))
    if frequency >= WEEK:
        return True
    return ((int(day_number) + int(offset)) * frequency) % WEEK < frequency


def day_number(reference: str | None = None) -> int:
    return parse_date(reference or today_iso()).toordinal()


def max_per_day() -> int:
    """Teto de disciplinas por dia (0 = sem teto). Uma unica configuracao."""
    return max(0, settings_service.get_int("today_max_disciplines", 5))


def _discipline_extras(discipline_id: int, reference: str) -> dict:
    """Assunto em aberto, ultimo contato e se ja estudou hoje."""
    current = query_one(
        "SELECT sub.id, sub.name FROM study_sessions s"
        " JOIN subjects sub ON sub.id = s.subject_id"
        " WHERE s.discipline_id = ? AND sub.status = 'em_andamento'"
        " ORDER BY s.date DESC, s.id DESC LIMIT 1",
        (discipline_id,))
    return {
        "current_subject_id": current["id"] if current else None,
        "current_subject": current["name"] if current else "",
        "studied_today": bool(scalar(
            "SELECT COUNT(*) FROM study_sessions WHERE discipline_id = ? AND date = ?",
            (discipline_id, reference), 0)),
        "last_date": scalar(
            "SELECT MAX(date) FROM study_sessions WHERE discipline_id = ?",
            (discipline_id,), None),
    }


def objectives(reference: str | None = None, limit: int | None = None) -> list[dict]:
    """As disciplinas do dia, na ordem de prioridade.

    Nao grava nada e nao depende de ciclo, bloco ou calendario.
    """
    reference = reference or today_iso()
    number = day_number(reference)
    rows = query_all("SELECT * FROM disciplines WHERE active = 1")

    prepared: list[dict] = []
    for row in rows:
        frequency = frequency_of(row)
        prepared.append({
            "id": row["id"],
            "name": _get(row, "name", ""),
            "short_name": _get(row, "short_name", "") or _get(row, "name", ""),
            "priority": _get(row, "priority", ""),
            "priority_label": PRIORITIES.get(_get(row, "priority", ""), ""),
            "priority_rank": priority_rank(_get(row, "priority")),
            "frequency": frequency,
            "frequency_label": frequency_label(frequency),
            "today": lands_on(number, frequency, row["id"]),
        })

    prepared.sort(key=lambda d: (d["priority_rank"], -d["frequency"], d["name"]))
    chosen = [d for d in prepared if d["today"]]

    # Dia sem nenhuma disciplina sorteada nao pode virar tela vazia: mostra as de
    # maior prioridade, marcadas como sugestao.
    fallback = False
    if not chosen and prepared:
        chosen = prepared[:3]
        fallback = True

    cap = max_per_day() if limit is None else limit
    if cap and len(chosen) > cap:
        chosen = chosen[:cap]

    for item in chosen:
        item.update(_discipline_extras(item["id"], reference))
        item["fallback"] = fallback
    return chosen


def open_subjects(limit: int = 12) -> list[dict]:
    """Assuntos em andamento - candidatos a "terminei este assunto".

    Ordena pelo ultimo contato: o que voce estudou por ultimo aparece primeiro.
    """
    rows = query_all(
        "SELECT sub.id, sub.name, sub.discipline_id, d.name AS discipline_name,"
        " d.short_name, COUNT(s.id) AS sessions, MAX(s.date) AS last_date,"
        " COALESCE(SUM(s.actual_minutes), 0) AS minutes"
        " FROM subjects sub"
        " JOIN disciplines d ON d.id = sub.discipline_id"
        " LEFT JOIN study_sessions s ON s.subject_id = sub.id"
        " WHERE sub.status = 'em_andamento'"
        " GROUP BY sub.id"
        " ORDER BY (last_date IS NULL), last_date DESC, sub.id DESC LIMIT ?",
        (limit,))
    return [dict(r) for r in rows]


def summary(reference: str | None = None) -> dict:
    """Resumo do dia. Tres numeros, nenhum grafico."""
    reference = reference or today_iso()
    return {
        "studies": int(scalar(
            "SELECT COUNT(*) FROM study_sessions WHERE date = ?", (reference,), 0)),
        "minutes": int(scalar(
            "SELECT COALESCE(SUM(actual_minutes), 0) FROM study_sessions WHERE date = ?",
            (reference,), 0)),
        "subjects_done": int(scalar(
            "SELECT COUNT(*) FROM subjects WHERE completed_at = ?", (reference,), 0)),
        "reviews_done": int(scalar(
            "SELECT COUNT(*) FROM reviews WHERE last_done_at = ?", (reference,), 0)),
    }
