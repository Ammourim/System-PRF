"""Testes do aviso de simulado e do simulado como sinal nas sugestoes."""

from app.db import insert, query_one
from app.services import adaptive
from app.services import mocks as mocks_service
from app.services import settings as settings_service
from app.utils import add_days, today_iso


def _mock(days_ago: int, name: str = "Simulado", total: int = 120, correct: int = 76) -> int:
    return insert(
        "INSERT INTO mock_exams (name, date, total, correct, wrong, percentage)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (name, add_days(today_iso(), -days_ago), total, correct, total - correct,
         round(correct / total * 100, 2)))


def _result(mock_id: int, discipline_id: int, total: int, correct: int) -> None:
    insert(
        "INSERT INTO mock_exam_results (mock_exam_id, discipline_id, total, correct, wrong,"
        " percentage) VALUES (?, ?, ?, ?, ?, ?)",
        (mock_id, discipline_id, total, correct, total - correct,
         round(correct / total * 100, 2)))


# ---------------------------------------------------------------- agendamento
def test_sem_simulado_recomenda_o_primeiro(ctx):
    status = mocks_service.status()
    assert status["state"] == "primeiro"
    assert status["is_due"] is True


def test_dentro_do_intervalo_nao_avisa(ctx):
    _mock(days_ago=3)
    status = mocks_service.status()
    assert status["state"] == "agendado"
    assert status["is_due"] is False
    assert status["days_left"] == 11  # quinzenal: 14 - 3


def test_vence_no_dia_exato(ctx):
    _mock(days_ago=14)
    status = mocks_service.status()
    assert status["state"] == "hoje"
    assert status["is_due"] is True
    assert status["days_left"] == 0


def test_avisa_quando_passa_do_intervalo(ctx):
    _mock(days_ago=20)
    status = mocks_service.status()
    assert status["state"] == "vencido"
    assert status["is_due"] is True
    assert status["days_left"] == -6
    assert status["days_since"] == 20


def test_frequencia_manual_desliga_o_aviso(ctx):
    _mock(days_ago=90)
    settings_service.set_value("mock_frequency", "manual")
    status = mocks_service.status()
    assert status["state"] == "manual"
    assert status["is_due"] is False


def test_frequencia_semanal_e_mensal(ctx):
    _mock(days_ago=10)
    settings_service.set_value("mock_frequency", "semanal")
    assert mocks_service.status()["is_due"] is True
    settings_service.set_value("mock_frequency", "mensal")
    assert mocks_service.status()["is_due"] is False


def test_adiar_silencia_sem_mudar_a_frequencia(ctx):
    _mock(days_ago=20)
    assert mocks_service.status()["is_due"] is True

    until = mocks_service.snooze(3)
    status = mocks_service.status()
    assert status["state"] == "adiado"
    assert status["is_due"] is False
    assert status["snoozed_until"] == until
    assert settings_service.get("mock_frequency") == "quinzenal"

    mocks_service.clear_snooze()
    assert mocks_service.status()["is_due"] is True


def test_adiamento_expira_sozinho(ctx):
    _mock(days_ago=20)
    settings_service.set_value("mock_snooze_until", add_days(today_iso(), -1))
    assert mocks_service.status()["is_due"] is True


def test_registrar_simulado_limpa_o_adiamento(client, app):
    with app.app_context():
        _mock(days_ago=20)
        mocks_service.snooze(7)
        assert mocks_service.status()["state"] == "adiado"

    client.post("/simulados/salvar", data={
        "name": "Simulado #02", "date": today_iso(), "total": "120", "correct": "80",
    }, follow_redirects=True)

    with app.app_context():
        status = mocks_service.status()
        assert settings_service.get("mock_snooze_until") == ""
        assert status["state"] == "agendado"  # o intervalo recomecou hoje
        assert status["is_due"] is False


def test_aviso_aparece_e_some_no_painel(client, app):
    with app.app_context():
        _mock(days_ago=20)
    assert "Simulado recomendado" in client.get("/").get_data(as_text=True)

    client.post("/simulados/adiar", data={"days": "3"}, follow_redirects=True)
    assert "Simulado recomendado" not in client.get("/").get_data(as_text=True)


def test_aviso_nao_cria_nada_nem_mexe_no_ciclo(client, app):
    """O aviso e informativo: nao gera simulado, sessao nem mexe na posicao."""
    from app.db import scalar
    from app.services import cycle as cycle_service

    with app.app_context():
        _mock(days_ago=30)
        posicao = cycle_service.active_cycle()["current_position"]
        blocos = cycle_service.total_blocks(cycle_service.active_cycle()["id"])

    client.get("/")
    client.get("/simulados/")

    with app.app_context():
        assert cycle_service.active_cycle()["current_position"] == posicao
        assert cycle_service.total_blocks(cycle_service.active_cycle()["id"]) == blocos
        assert scalar("SELECT COUNT(*) FROM mock_exams", (), 0) == 1
        assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 0


# ------------------------------------------------- simulado nas sugestoes
def test_simulado_ruim_pesa_mesmo_com_questoes_boas(ctx):
    """Vai bem nas questoes soltas, cai no simulado -> sugere aumentar."""
    insert("INSERT INTO questions (date, discipline_id, total, correct, wrong, percentage)"
           " VALUES (?, 1, 40, 34, 6, 85.0)", (today_iso(),))
    mock_id = _mock(days_ago=5)
    _result(mock_id, 1, 30, 12)  # 40% no simulado

    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 1)
    assert sugestao["direction"] == "aumentar"
    assert sugestao["mock_accuracy"] == 40.0
    assert any("cai no simulado" in r for r in sugestao["reasons"])


def test_simulado_segura_a_reducao(ctx):
    """Desempenho alto no dia a dia, mas simulado na faixa de atencao -> manter."""
    # Fisica e complementar e comeca 'nao iniciada' - so faz sentido avaliar depois de iniciada.
    ctx.execute("UPDATE disciplines SET status = 'em_andamento' WHERE id = 14")
    ctx.commit()
    insert("INSERT INTO questions (date, discipline_id, total, correct, wrong, percentage)"
           " VALUES (?, 14, 40, 36, 4, 90.0)", (today_iso(),))
    mock_id = _mock(days_ago=5)
    _result(mock_id, 14, 20, 13)  # 65%

    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 14)
    assert sugestao["direction"] == "manter"
    assert any("nao confirma o bom desempenho" in r for r in sugestao["reasons"])


def test_disciplina_nao_iniciada_ignora_o_simulado(ctx):
    """Nao iniciada indo mal no simulado e esperado - nao vira sugestao de aumentar."""
    mock_id = _mock(days_ago=5)
    _result(mock_id, 6, 8, 2)  # Informatica, ainda 'nao iniciada'
    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 6)
    assert sugestao["direction"] == "manter"
    assert any("nao iniciada" in r for r in sugestao["reasons"])


def test_simulado_vira_o_sinal_quando_faltam_questoes(ctx):
    ctx.execute("UPDATE disciplines SET status = 'em_andamento' WHERE id = 6")
    ctx.commit()
    mock_id = _mock(days_ago=5)
    _result(mock_id, 6, 8, 2)  # Informatica: 25%, sem questoes no dia a dia

    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 6)
    assert sugestao["direction"] == "aumentar"
    assert any("simulado ja mostra" in r for r in sugestao["reasons"])


def test_simulado_com_poucas_questoes_e_ignorado(ctx):
    insert("INSERT INTO questions (date, discipline_id, total, correct, wrong, percentage)"
           " VALUES (?, 1, 40, 34, 6, 85.0)", (today_iso(),))
    mock_id = _mock(days_ago=5)
    _result(mock_id, 1, 3, 0)  # amostra pequena demais para concluir algo

    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 1)
    assert sugestao["direction"] != "aumentar"
    assert not any("simulado" in r.lower() for r in sugestao["reasons"])


def test_sugestao_com_simulado_continua_sem_escrever_no_banco(ctx):
    mock_id = _mock(days_ago=5)
    _result(mock_id, 1, 30, 9)
    antes = query_one("SELECT target_minutes FROM disciplines WHERE id = 1")["target_minutes"]
    adaptive.suggestions(days=60)
    depois = query_one("SELECT target_minutes FROM disciplines WHERE id = 1")["target_minutes"]
    assert antes == depois
