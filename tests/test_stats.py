"""Testes dos calculos de desempenho e das sugestoes de ajuste."""

from app.db import insert
from app.services import adaptive, stats
from app.utils import add_days, today_iso


def _questions(discipline_id, total, correct, days_ago=0, subject_id=None):
    date = add_days(today_iso(), -days_ago)
    insert(
        "INSERT INTO questions (date, discipline_id, subject_id, total, correct, wrong,"
        " percentage) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date, discipline_id, subject_id, total, correct, total - correct,
         round(correct / total * 100, 2)))


def _session(discipline_id, minutes, days_ago=0):
    insert(
        "INSERT INTO study_sessions (date, discipline_id, type, planned_minutes,"
        " actual_minutes) VALUES (?, ?, 'questoes', ?, ?)",
        (add_days(today_iso(), -days_ago), discipline_id, minutes, minutes))


def test_overall_agrega_periodo(ctx):
    _questions(1, 20, 15)
    _questions(1, 30, 21, days_ago=3)
    _questions(1, 10, 5, days_ago=60)  # fora da janela de 30 dias
    _session(1, 90)

    resumo = stats.overall(days=30)
    assert resumo["questions"] == 50
    assert resumo["correct"] == 36
    assert resumo["accuracy"] == 72.0
    assert resumo["minutes"] == 90


def test_by_discipline_traz_todas_mesmo_sem_dados(ctx):
    _questions(1, 20, 10)
    linhas = stats.by_discipline(days=30)
    assert len(linhas) == 14
    com_dados = [r for r in linhas if r["questions"]]
    assert len(com_dados) == 1 and com_dados[0]["accuracy"] == 50.0
    sem_dados = [r for r in linhas if not r["questions"]][0]
    assert sem_dados["accuracy"] is None


def test_pontos_fracos_por_assunto(ctx):
    subject_bom = insert("INSERT INTO subjects (discipline_id, name) VALUES (1, 'Sinalizacao')")
    subject_ruim = insert("INSERT INTO subjects (discipline_id, name) VALUES (1, 'Infracoes')")
    _questions(1, 20, 18, subject_id=subject_bom)
    _questions(1, 20, 9, subject_id=subject_ruim)

    fracos = stats.weak_points(days=90, min_questions=10)
    assert [f["subject_name"] for f in fracos] == ["Infracoes"]
    assert fracos[0]["accuracy"] == 45.0


def test_evolucao_compara_periodos(ctx):
    _questions(1, 20, 10, days_ago=45)   # periodo anterior: 50%
    _questions(1, 20, 16, days_ago=5)    # periodo atual: 80%
    evolucao = stats.evolution(days=30)
    assert evolucao["current"]["accuracy"] == 80.0
    assert evolucao["previous"]["accuracy"] == 50.0
    assert evolucao["accuracy_delta"] == 30.0


def test_serie_diaria_tem_um_ponto_por_dia(ctx):
    _session(1, 60, days_ago=1)
    serie = stats.daily_series(days=7)
    assert len(serie) == 7
    assert sum(p["minutes"] for p in serie) == 60


def test_resumo_de_hoje(ctx):
    _session(1, 120)
    _questions(1, 30, 24)
    insert("INSERT INTO college_sessions (date, minutes) VALUES (?, 45)", (today_iso(),))
    resumo = stats.today_summary()
    assert resumo["prf_minutes"] == 120
    assert resumo["questions"] == 30
    assert resumo["accuracy"] == 80.0
    assert resumo["college_minutes"] == 45


def test_sugestao_aumenta_quando_desempenho_baixo(ctx):
    _questions(1, 40, 18)  # 45% em CTB (incidencia 25%)
    _session(1, 120)
    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 1)
    assert sugestao["direction"] == "aumentar"
    assert sugestao["suggested_target"] == sugestao["current_target"] + adaptive.STEP_MINUTES
    assert any("abaixo do limiar" in r for r in sugestao["reasons"])


def test_sugestao_mantem_quando_amostra_pequena(ctx):
    _questions(1, 5, 1)
    _session(1, 60)
    sugestao = next(s for s in adaptive.suggestions(days=60) if s["id"] == 1)
    assert sugestao["direction"] == "manter"
    assert sugestao["delta"] == 0
    assert any("Amostra pequena" in r for r in sugestao["reasons"])


def test_sugestao_nao_altera_o_banco(ctx):
    _questions(1, 40, 10)
    antes = ctx.execute("SELECT target_minutes FROM disciplines WHERE id = 1").fetchone()[0]
    adaptive.suggestions(days=60)
    depois = ctx.execute("SELECT target_minutes FROM disciplines WHERE id = 1").fetchone()[0]
    assert antes == depois


def test_aplicar_ajuste_altera_meta(ctx):
    adaptive.apply_target(1, 480)
    assert ctx.execute(
        "SELECT target_minutes FROM disciplines WHERE id = 1").fetchone()[0] == 480


def test_relatorio_de_ciclo(ctx):
    from app.services import cycle as cycle_service

    cycle = cycle_service.active_cycle()
    _session(1, 300)
    _questions(1, 100, 71)
    relatorio = adaptive.cycle_report(cycle)
    assert relatorio["minutes"] == 300
    assert relatorio["questions"] == 100
    assert relatorio["accuracy"] == 71.0
    assert relatorio["goal_minutes"] == 1800
    assert relatorio["minutes_pct"] == round(300 / 1800 * 100, 1)
