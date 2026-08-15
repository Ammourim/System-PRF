"""Funcoes utilitarias: parsing de formulario, datas e formatacao."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO = "%Y-%m-%d"
DEFAULT_TIMEZONE = "America/Sao_Paulo"


# --------------------------------------------------------------------------
# Datas
# --------------------------------------------------------------------------
# O horario NUNCA vem do relogio do servidor: hospedado, ele roda em UTC, e no
# Brasil (UTC-3) tudo registrado depois das 21h seria gravado com a data do dia
# seguinte - errando silenciosamente as datas de sessoes, questoes e revisoes.
@lru_cache(maxsize=4)
def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        # Fuso invalido nao pode derrubar a aplicacao: cai no padrao.
        return ZoneInfo(DEFAULT_TIMEZONE)


def timezone() -> ZoneInfo:
    """Fuso configurado em PRF_TIMEZONE.

    Lido a cada chamada (e cacheado por nome) porque o .env so e carregado
    dentro de create_app(), depois deste modulo ser importado.
    """
    return _zone(os.environ.get("PRF_TIMEZONE") or DEFAULT_TIMEZONE)


def now() -> datetime:
    """Agora, com fuso - use no lugar de datetime.now()."""
    return datetime.now(timezone())


def today() -> date:
    return now().date()


def today_iso() -> str:
    return now().strftime(ISO)


def parse_date(value: str | None, default: date | None = None) -> date:
    if not value:
        return default or today()
    try:
        return datetime.strptime(value.strip(), ISO).date()
    except ValueError:
        return default or today()


def to_iso(value: date) -> str:
    return value.strftime(ISO)


def add_days(value: date | str, days: int) -> str:
    if isinstance(value, str):
        value = parse_date(value)
    return to_iso(value + timedelta(days=days))


def days_between(start: str | date, end: str | date) -> int:
    a = parse_date(start) if isinstance(start, str) else start
    b = parse_date(end) if isinstance(end, str) else end
    return (b - a).days


def date_br(value: str | date | None) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        value = parse_date(value)
    return value.strftime("%d/%m/%Y")


# --------------------------------------------------------------------------
# Parsing de formulario (tolerante: campo vazio nunca quebra a tela)
# --------------------------------------------------------------------------
def as_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def as_float(value, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def as_opt_int(value) -> int | None:
    """Converte para int ou None (para chaves estrangeiras opcionais)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"0", "-", "none", "None"}:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def as_bool(value) -> int:
    return 1 if str(value).strip().lower() in {"1", "on", "true", "sim", "yes"} else 0


def as_text(value, default: str = "", max_length: int = 4000) -> str:
    if value is None:
        return default
    return str(value).strip()[:max_length]


def parse_minutes(value, default: int = 0) -> int:
    """Aceita '90', '1:30', '1h30', '1,5h' e devolve minutos."""
    if value is None:
        return default
    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return default
    if ":" in text:
        h, _, m = text.partition(":")
        return as_int(h) * 60 + as_int(m)
    if "h" in text:
        h, _, m = text.partition("h")
        hours = as_float(h, 0) or 0
        minutes = as_int(m.replace("min", "").replace("m", ""), 0)
        if float(hours).is_integer():
            return int(hours) * 60 + minutes
        return int(round(hours * 60)) + minutes
    return as_int(text, default)


# --------------------------------------------------------------------------
# Formatacao
# --------------------------------------------------------------------------
def fmt_minutes(minutes: int | float | None) -> str:
    """1875 -> '31h15'."""
    if not minutes:
        return "0h00"
    minutes = int(round(minutes))
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60}h{minutes % 60:02d}"


def fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}".replace(".", ",") + "%"


def fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.{digits}f}".replace(".", ",")


def percentage(correct: int, total: int) -> float:
    """Percentual de acerto, arredondado em 2 casas. Total 0 -> 0.0."""
    if not total:
        return 0.0
    return round(correct / total * 100, 2)


def performance_level(pct: float | None, low: float = 60.0, mid: float = 70.0) -> str:
    """Classifica um percentual: 'ruim' | 'atencao' | 'bom' | 'sem_dados'."""
    if pct is None:
        return "sem_dados"
    if pct < low:
        return "ruim"
    if pct < mid:
        return "atencao"
    return "bom"
