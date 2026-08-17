"""O ciclo: "qual disciplina eu estudo agora?"

O ciclo e uma SEQUENCIA fixa de disciplinas mais uma POSICAO. Nada de
calendario, minutos, blocos ou metas.

    sequencia:  CTB, Portugues, Administrativo, Constitucional, CTB, ...
    posicao:    ^

A tela HOJE mostra a disciplina da posicao atual - uma so. A posicao avanca
em um unico momento: quando o usuario conclui um registro de estudo. Abrir o
formulario e desistir nao avanca. Nao estudar hoje nao avanca. Amanha voce
continua exatamente de onde parou (compativel com a escala 12x36).

A FREQUENCIA de cada disciplina diz quantas vezes ela aparece na sequencia; a
PRIORIDADE ordena quem vem primeiro. As duas coisas sao diferentes de
proposito: prioridade nao faz ninguem aparecer mais vezes do que a frequencia
configurada.

Revisao espacada nao passa por aqui: e independente do ciclo (services/reviews.py).
"""

from __future__ import annotations

from ..db import query_all, query_one, scalar
from ..utils import today_iso
from . import settings as settings_service
from .cycle import PRIORITIES, priority_rank  # noqa: F401  (vocabulario unico)

MAX_FREQUENCY = 7

# Frequencia padrao por prioridade (vezes por ciclo). Editavel por disciplina.
PRIORITY_FREQUENCY: dict[str, int] = {
    "maxima": 3,
    "alta": 1,
    "media": 1,
    "baixa": 1,
}
DEFAULT_FREQUENCY = 1

FREQUENCY_LABELS: dict[int, str] = {
    1: "1x por ciclo",
    2: "2x por ciclo",
    3: "3x por ciclo",
    4: "4x por ciclo",
    5: "5x por ciclo",
    6: "6x por ciclo",
    7: "7x por ciclo",
}

POSITION_KEY = "cycle_position"


# --------------------------------------------------------------------------
# Frequencia
# --------------------------------------------------------------------------
def default_frequency(priority) -> int:
    return PRIORITY_FREQUENCY.get(str(priority or ""), DEFAULT_FREQUENCY)


def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def frequency_of(row) -> int:
    """Frequencia efetiva da disciplina (1 a 7). 0 = deduzir da prioridade."""
    value = int(_get(row, "frequency", 0) or 0)
    if value <= 0:
        value = default_frequency(_get(row, "priority"))
    return max(1, min(MAX_FREQUENCY, value))


def frequency_label(value: int) -> str:
    return FREQUENCY_LABELS.get(max(1, min(MAX_FREQUENCY, int(value or 1))), "")


# --------------------------------------------------------------------------
# Montagem da sequencia
# --------------------------------------------------------------------------
def active_disciplines() -> list[dict]:
    """Disciplinas do ciclo, na ordem de prioridade. Inativa nao entra."""
    rows = query_all("SELECT * FROM disciplines WHERE active = 1")
    items = [{
        "id": row["id"],
        "name": _get(row, "name", ""),
        "short_name": _get(row, "short_name", "") or _get(row, "name", ""),
        "priority": _get(row, "priority", ""),
        "priority_label": PRIORITIES.get(_get(row, "priority", ""), ""),
        "priority_rank": priority_rank(_get(row, "priority")),
        "incidence": float(_get(row, "incidence", 0) or 0),
        "frequency": frequency_of(row),
    } for row in rows]
    items.sort(key=lambda d: (d["priority_rank"], -d["incidence"], d["name"]))
    return items


def build_sequence(disciplines: list[dict]) -> list[dict]:
    """Espalha cada disciplina pela sequencia conforme a frequencia dela.

    Cada aparicao recebe uma posicao fracionaria em [0, 1):

        posicao = (i + fase) / frequencia

    `i` e o numero da aparicao e `fase` desloca a disciplina conforme a ordem de
    prioridade. Sem a fase, todas as disciplinas de frequencia 1 cairiam no mesmo
    ponto e a sequencia ficaria empilhada; com ela, as repeticoes de quem aparece
    mais vezes ficam distribuidas entre as demais - e a ordem de prioridade
    continua valendo como criterio de desempate.

    Exemplo (CTB 3x, Portugues 2x, oito disciplinas 1x):

        CTB, Portugues, Administrativo, Constitucional, CTB, Informatica,
        RLM, Portugues, Leg. Especial, CTB, Etica, Penal, Processo Penal
    """
    total = len(disciplines)
    if not total:
        return []

    entradas: list[tuple[float, int, int, dict]] = []
    for ordem, item in enumerate(disciplines):
        fase = ordem / total
        for i in range(item["frequency"]):
            entradas.append(((i + fase) / item["frequency"], item["frequency"], ordem, item))

    # Empate de posicao: quem aparece MENOS vezes passa na frente. Assim a
    # disciplina repetida nao gruda com a copia seguinte dela mesma.
    entradas.sort(key=lambda e: e[:3])
    return [dict(item, position=posicao)
            for posicao, (_, _, _, item) in enumerate(entradas, start=1)]


def sequence() -> list[dict]:
    """A sequencia do ciclo, recalculada a partir das disciplinas ativas."""
    return build_sequence(active_disciplines())


# --------------------------------------------------------------------------
# Posicao
# --------------------------------------------------------------------------
def position(total: int | None = None) -> int:
    """Indice atual na sequencia (base 0). Sempre dentro dos limites.

    O modulo protege o caso em que a sequencia encolheu (disciplina desativada,
    frequencia reduzida): a posicao nunca aponta para fora da lista.
    """
    total = len(sequence()) if total is None else total
    if not total:
        return 0
    return max(0, settings_service.get_int(POSITION_KEY, 0)) % total


def set_position(value: int) -> None:
    settings_service.set_value(POSITION_KEY, max(0, int(value)))


def reset_position() -> None:
    """Volta o ciclo para o inicio. Nao apaga estudo, questao nem revisao."""
    set_position(0)


def current() -> dict | None:
    """A disciplina da vez. None quando nao ha disciplina ativa."""
    items = sequence()
    if not items:
        return None
    indice = position(len(items))
    atual = dict(items[indice])
    atual["total"] = len(items)
    atual["next_name"] = items[(indice + 1) % len(items)]["name"]
    return atual


def advance() -> dict | None:
    """Anda uma casa. Chamado APENAS quando um estudo e concluido."""
    items = sequence()
    if not items:
        return None
    set_position((position(len(items)) + 1) % len(items))
    return current()


# --------------------------------------------------------------------------
# Apoio da tela HOJE
# --------------------------------------------------------------------------
def last_study() -> dict | None:
    row = query_one(
        "SELECT s.date, d.name AS discipline_name, sub.name AS subject_name"
        " FROM study_sessions s"
        " LEFT JOIN disciplines d ON d.id = s.discipline_id"
        " LEFT JOIN subjects sub ON sub.id = s.subject_id"
        " ORDER BY s.date DESC, s.id DESC LIMIT 1")
    return dict(row) if row else None


def open_subjects(limit: int = 8) -> list[dict]:
    """Assuntos em andamento - candidatos a "concluí este assunto"."""
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
