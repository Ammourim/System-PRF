"""Quando fazer o proximo simulado - calculo, nunca criacao automatica.

O sistema so informa que a frequencia configurada venceu. Nao cria simulado,
nao insere bloco no ciclo e nao gera pendencia. Se voce nao quiser fazer agora,
o aviso pode ser adiado e o ciclo segue exatamente igual.
"""

from __future__ import annotations

from ..db import query_one
from ..utils import add_days, days_between, today_iso
from . import settings as settings_service

# Frequencia configurada -> intervalo em dias. 'manual' desliga o aviso.
FREQUENCY_DAYS = {"semanal": 7, "quinzenal": 14, "mensal": 30, "manual": None}

FREQUENCY_LABELS = {"semanal": "Semanal", "quinzenal": "Quinzenal", "mensal": "Mensal",
                    "manual": "Manual (sem aviso)"}


def frequency_days() -> int | None:
    return FREQUENCY_DAYS.get(settings_service.get("mock_frequency", "quinzenal"), 14)


def last_mock():
    return query_one("SELECT * FROM mock_exams ORDER BY date DESC, id DESC LIMIT 1")


def status(reference: str | None = None) -> dict:
    """Situacao do proximo simulado.

    Retorna sempre um dict com 'state', que vale:
      * 'manual'    - frequencia desligada, nenhum aviso;
      * 'primeiro'  - nenhum simulado registrado ainda;
      * 'vencido'   - passou do intervalo configurado;
      * 'hoje'      - vence hoje;
      * 'agendado'  - ainda falta tempo;
      * 'adiado'    - o usuario adiou o aviso.
    """
    today = reference or today_iso()
    days = frequency_days()
    last = last_mock()
    frequency = settings_service.get("mock_frequency", "quinzenal")

    data = {
        "frequency": frequency,
        "frequency_label": FREQUENCY_LABELS.get(frequency, frequency),
        "interval_days": days,
        "last": last,
        "days_since": days_between(last["date"], today) if last else None,
        "next_date": None,
        "days_left": None,
        "state": "manual",
        "is_due": False,
    }

    if days is None:
        return data

    if last is None:
        data.update(state="primeiro", is_due=True, next_date=today, days_left=0)
    else:
        next_date = add_days(last["date"], days)
        days_left = days_between(today, next_date)
        data["next_date"] = next_date
        data["days_left"] = days_left
        if days_left < 0:
            data.update(state="vencido", is_due=True)
        elif days_left == 0:
            data.update(state="hoje", is_due=True)
        else:
            data.update(state="agendado", is_due=False)

    # Adiamento explicito do aviso (nao mexe na frequencia nem no ciclo).
    snooze = settings_service.get("mock_snooze_until", "")
    if snooze and snooze > today and data["is_due"]:
        data.update(state="adiado", is_due=False, snoozed_until=snooze)

    return data


def snooze(days: int, reference: str | None = None) -> str:
    """Adia apenas o aviso do painel. Retorna a data ate a qual fica silenciado."""
    until = add_days(reference or today_iso(), max(1, int(days)))
    settings_service.set_value("mock_snooze_until", until)
    return until


def clear_snooze() -> None:
    settings_service.set_value("mock_snooze_until", "")


def last_results_by_discipline() -> dict[int, dict]:
    """Desempenho por disciplina no ultimo simulado que tenha lancamento.

    Usado pelas sugestoes de ajuste: o simulado e um sinal mais confiavel que a
    questao avulsa, porque foi feito sob pressao de tempo.
    """
    from ..db import query_all

    mock = query_one(
        "SELECT m.* FROM mock_exams m"
        " WHERE EXISTS (SELECT 1 FROM mock_exam_results r WHERE r.mock_exam_id = m.id)"
        " ORDER BY m.date DESC, m.id DESC LIMIT 1")
    if mock is None:
        return {}
    rows = query_all(
        "SELECT * FROM mock_exam_results WHERE mock_exam_id = ?", (mock["id"],))
    return {
        row["discipline_id"]: {
            "percentage": row["percentage"],
            "total": row["total"],
            "correct": row["correct"],
            "mock_name": mock["name"],
            "mock_date": mock["date"],
        }
        for row in rows
    }
