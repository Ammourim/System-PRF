"""Testes das funcoes puras de calculo e parsing."""

from app.utils import (add_days, days_between, fmt_minutes, fmt_pct, parse_minutes,
                       percentage, performance_level)


def test_percentage_basico():
    assert percentage(14, 20) == 70.0
    assert percentage(0, 20) == 0.0
    assert percentage(20, 20) == 100.0


def test_percentage_total_zero_nao_quebra():
    assert percentage(0, 0) == 0.0


def test_percentage_arredonda_em_duas_casas():
    assert percentage(1, 3) == 33.33


def test_parse_minutes_aceita_formatos():
    assert parse_minutes("45") == 45
    assert parse_minutes("1:30") == 90
    assert parse_minutes("1h30") == 90
    assert parse_minutes("2h") == 120
    assert parse_minutes("1,5h") == 90
    assert parse_minutes("", 60) == 60
    assert parse_minutes("texto invalido", 30) == 30


def test_fmt_minutes():
    assert fmt_minutes(1875) == "31h15"
    assert fmt_minutes(0) == "0h00"
    assert fmt_minutes(60) == "1h00"


def test_fmt_pct_usa_virgula():
    assert fmt_pct(71.25) == "71,2%" or fmt_pct(71.25) == "71,3%"
    assert fmt_pct(None) == "-"


def test_datas():
    assert add_days("2026-01-01", 7) == "2026-01-08"
    assert days_between("2026-01-01", "2026-01-15") == 14


def test_performance_level():
    assert performance_level(51) == "ruim"
    assert performance_level(65) == "atencao"
    assert performance_level(80) == "bom"
    assert performance_level(None) == "sem_dados"
