"""O horario tem que vir do fuso configurado, nunca do relogio do servidor.

Hospedado, o servidor roda em UTC: sem isso, tudo registrado depois das 21h no
Brasil seria gravado com a data do dia seguinte.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app import utils


def _reset_cache():
    utils._zone.cache_clear()


def test_today_respeita_a_variavel_de_ambiente(monkeypatch):
    """Dois fusos extremos (UTC+14 e UTC-12) nunca estao no mesmo dia."""
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "Pacific/Kiritimati")   # UTC+14
    mais_cedo = utils.today()
    monkeypatch.setenv("PRF_TIMEZONE", "Etc/GMT+12")           # UTC-12
    mais_tarde = utils.today()
    assert mais_cedo != mais_tarde
    assert (mais_cedo - mais_tarde).days == 1
    _reset_cache()


def test_padrao_e_horario_de_brasilia(monkeypatch):
    _reset_cache()
    monkeypatch.delenv("PRF_TIMEZONE", raising=False)
    assert str(utils.timezone()) == "America/Sao_Paulo"
    assert utils.today() == datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    _reset_cache()


def test_fuso_invalido_cai_no_padrao_sem_quebrar(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "Fuso/Que_Nao_Existe")
    assert str(utils.timezone()) == "America/Sao_Paulo"
    assert utils.today_iso()  # nao levanta excecao
    _reset_cache()


def test_variavel_vazia_cai_no_padrao(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "")
    assert str(utils.timezone()) == "America/Sao_Paulo"
    _reset_cache()


def test_today_iso_e_today_concordam(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "America/Sao_Paulo")
    assert utils.today_iso() == utils.to_iso(utils.today())
    _reset_cache()


def test_now_traz_fuso(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "America/Sao_Paulo")
    agora = utils.now()
    assert agora.tzinfo is not None
    assert agora.utcoffset().total_seconds() == -3 * 3600
    _reset_cache()


def test_sessao_registrada_usa_a_data_local(client, app, monkeypatch):
    """Registro pela rota grava a data do fuso configurado, nao a do servidor."""
    _reset_cache()
    monkeypatch.setenv("PRF_TIMEZONE", "America/Sao_Paulo")
    esperado = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")

    client.post("/sessoes/salvar", data={
        "discipline_id": "1", "type": "teoria", "actual_minutes": "60",
    }, follow_redirects=True)

    with app.app_context():
        from app.db import query_one
        assert query_one("SELECT date FROM study_sessions ORDER BY id DESC")["date"] == esperado
    _reset_cache()
