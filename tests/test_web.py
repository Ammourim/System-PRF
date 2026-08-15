"""Testes de ponta a ponta pelas rotas HTTP (fluxo real do usuario)."""

from app.db import get_db, query_all, query_one, scalar
from app.services import cycle as cycle_service
from app.utils import today_iso


def test_todas_as_paginas_abrem(client):
    for url in ["/", "/ciclo/", "/ciclo/montar", "/sessoes/", "/sessoes/nova", "/questoes/",
                "/revisoes/", "/erros/", "/simulados/", "/simulados/cronometro",
                "/desempenho/", "/desempenho/ajustes", "/disciplinas/", "/taf/",
                "/taf/treinos/", "/faculdade/", "/configuracoes/", "/dados/"]:
        response = client.get(url)
        assert response.status_code == 200, f"{url} retornou {response.status_code}"


def test_nenhum_get_altera_estado(client, app):
    """Invariante do sistema: so uma acao explicita (POST) muda alguma coisa.

    Abrir qualquer tela - inclusive as de sugestao e relatorio - nao pode mexer na
    posicao do ciclo, marcar bloco, criar revisao nem alterar metas.
    """
    from app.seed import seed_demo

    with app.app_context():
        seed_demo(get_db())

    def snapshot():
        with app.app_context():
            cycle = cycle_service.active_cycle()
            return {
                "position": cycle["current_position"],
                "blocks_done": scalar("SELECT COUNT(*) FROM cycle_blocks WHERE done = 1", (), 0),
                "sessions": scalar("SELECT COUNT(*) FROM study_sessions", (), 0),
                "questions": scalar("SELECT COUNT(*) FROM questions", (), 0),
                "reviews": scalar("SELECT COUNT(*) FROM reviews", (), 0),
                "mocks": scalar("SELECT COUNT(*) FROM mock_exams", (), 0),
                "targets": scalar("SELECT SUM(target_minutes) FROM disciplines", (), 0),
                "review_dates": scalar("SELECT group_concat(next_date) FROM reviews", (), ""),
                "workouts": scalar("SELECT COUNT(*) FROM taf_workouts", (), 0),
                "workout_sessions": scalar(
                    "SELECT COUNT(*) FROM taf_workout_sessions", (), 0),
                "workout_sets": scalar("SELECT COUNT(*) FROM taf_session_sets", (), 0),
            }

    before = snapshot()
    with app.app_context():
        cycle_id = cycle_service.active_cycle()["id"]
    for url in ["/", "/ciclo/", "/ciclo/montar", f"/ciclo/{cycle_id}/relatorio", "/sessoes/",
                "/sessoes/nova", "/questoes/", "/revisoes/", "/erros/", "/simulados/",
                "/simulados/cronometro", "/desempenho/", "/desempenho/ajustes",
                "/disciplinas/", "/taf/", "/taf/treinos/", "/faculdade/", "/configuracoes/",
                "/dados/"]:
        assert client.get(url).status_code == 200, url
    for url in ["/", "/desempenho/ajustes", "/revisoes/"]:  # abrir duas vezes tambem nao muda
        client.get(url)

    assert snapshot() == before


def test_registrar_sessao_com_questoes_e_avanco(client, app):
    with app.app_context():
        cycle = cycle_service.active_cycle()
        block = cycle_service.next_block(cycle)
        block_id, discipline_id = block["id"], block["discipline_id"]

    response = client.post("/sessoes/salvar", data={
        "date": today_iso(),
        "discipline_id": str(discipline_id),
        "subject_name": "Infracoes",
        "type": "questoes",
        "actual_minutes": "45",
        "questions_total": "20",
        "questions_correct": "14",
        "notes": "confundi penalidade com medida administrativa",
        "block_id": str(block_id),
        "advance_cycle": "1",
        "create_review": "1",
    }, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        session = query_one("SELECT * FROM study_sessions ORDER BY id DESC LIMIT 1")
        assert session["actual_minutes"] == 45
        assert session["subject_id"] is not None

        question = query_one("SELECT * FROM questions WHERE session_id = ?", (session["id"],))
        assert question["total"] == 20 and question["correct"] == 14
        assert question["percentage"] == 70.0

        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 1
        assert cycle_service.active_cycle()["current_position"] == 2
        assert query_one("SELECT done FROM cycle_blocks WHERE id = ?", (block_id,))["done"] == 1


def test_sessao_sem_tempo_e_rejeitada(client, app):
    client.post("/sessoes/salvar", data={
        "date": today_iso(), "discipline_id": "1", "type": "teoria", "actual_minutes": "",
    }, follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 0


def test_acertos_nao_passam_do_total(client, app):
    client.post("/questoes/salvar", data={
        "date": today_iso(), "discipline_id": "1", "total": "10", "correct": "50",
    }, follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
        assert row["correct"] == 10 and row["percentage"] == 100.0


def test_assunto_digitado_e_criado_uma_vez_so(client, app):
    for _ in range(2):
        client.post("/questoes/salvar", data={
            "date": today_iso(), "discipline_id": "1", "subject_name": "Sinalizacao",
            "total": "10", "correct": "8",
        }, follow_redirects=True)
    with app.app_context():
        rows = query_all("SELECT * FROM subjects WHERE lower(name) = 'sinalizacao'")
        assert len(rows) == 1


def test_fluxo_simulado_com_resultado_por_disciplina(client, app):
    client.post("/simulados/salvar", data={
        "name": "Simulado #01", "date": today_iso(), "banca": "Cebraspe",
        "total": "120", "correct": "76", "total_minutes": "285", "planned_minutes": "300",
    }, follow_redirects=True)
    with app.app_context():
        mock = query_one("SELECT * FROM mock_exams ORDER BY id DESC LIMIT 1")
        assert mock["percentage"] == 63.33
        mock_id = mock["id"]

    client.post(f"/simulados/{mock_id}/resultado", data={
        "discipline_id": "1", "total": "30", "correct": "21",
    }, follow_redirects=True)
    # Lancar de novo a mesma disciplina atualiza em vez de duplicar.
    client.post(f"/simulados/{mock_id}/resultado", data={
        "discipline_id": "1", "total": "30", "correct": "24", "recalc_total": "1",
    }, follow_redirects=True)

    with app.app_context():
        results = query_all("SELECT * FROM mock_exam_results WHERE mock_exam_id = ?", (mock_id,))
        assert len(results) == 1
        assert results[0]["correct"] == 24 and results[0]["percentage"] == 80.0
        mock = query_one("SELECT * FROM mock_exams WHERE id = ?", (mock_id,))
        assert mock["total"] == 30 and mock["correct"] == 24

    assert client.get(f"/simulados/{mock_id}").status_code == 200


def test_erro_vira_revisao(client, app):
    client.post("/erros/salvar", data={
        "date": today_iso(), "discipline_id": "1", "subject_name": "Infracoes",
        "category": "C", "question_ref": "multa x medida administrativa",
        "explanation": "medida administrativa nao e penalidade",
    }, follow_redirects=True)
    with app.app_context():
        mistake = query_one("SELECT * FROM mistakes ORDER BY id DESC LIMIT 1")
        assert mistake["category"] == "C"
        mistake_id = mistake["id"]

    client.post(f"/erros/{mistake_id}/revisar", follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM reviews WHERE method = 'caderno_erros'", (), 0) == 1
        assert query_one("SELECT status FROM mistakes WHERE id = ?",
                         (mistake_id,))["status"] == "revisado"


def test_configuracoes_persistem(client, app):
    client.post("/configuracoes/salvar", data={
        "prf_goal_minutes": "1500", "questions_goal_per_folga": "60",
        "review_intervals": "2,6,14", "block_long": "100",
    }, follow_redirects=True)
    with app.app_context():
        from app.services import settings as settings_service
        assert settings_service.get_int("prf_goal_minutes") == 1500
        assert settings_service.get_int("questions_goal_per_folga") == 60
        assert settings_service.get_list_int("review_intervals") == [2, 6, 14]


def test_intervalos_invalidos_nao_apagam_os_atuais(client, app):
    client.post("/configuracoes/salvar", data={"review_intervals": "abc, ,-"},
                follow_redirects=True)
    with app.app_context():
        from app.services import settings as settings_service
        assert settings_service.get_list_int("review_intervals") == [1, 7, 15, 30, 60]


def test_ajuste_do_ciclo_so_muda_apos_aceite(client, app):
    with app.app_context():
        before = query_one("SELECT target_minutes FROM disciplines WHERE id = 1")["target_minutes"]
    client.get("/desempenho/ajustes")
    with app.app_context():
        after = query_one("SELECT target_minutes FROM disciplines WHERE id = 1")["target_minutes"]
    assert before == after  # so visualizar nunca altera nada

    client.post("/desempenho/ajustes/aplicar",
                data={"discipline_id": "1", "minutes": "450"}, follow_redirects=True)
    with app.app_context():
        assert query_one("SELECT target_minutes FROM disciplines WHERE id = 1")[
            "target_minutes"] == 450


def test_montar_ciclo_gera_blocos(client, app):
    with app.app_context():
        disciplines = query_all("SELECT id FROM disciplines ORDER BY id LIMIT 3")
        ids = [d["id"] for d in disciplines]

    data = {"name": "Ciclo teste", "start_date": today_iso(), "days": "14",
            "goal_minutes": "1800", "goal_questions": "350"}
    for did in ids:
        data[f"target_{did}"] = "180"
        data[f"block_{did}"] = "60"
    response = client.post("/ciclo/montar", data=data, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        cycle = cycle_service.active_cycle()
        assert cycle["name"] == "Ciclo teste"
        assert cycle_service.total_blocks(cycle["id"]) == 9  # 3 disciplinas x 3 blocos
        assert cycle["current_position"] == 1


def test_relatorio_de_ciclo_abre(client, app):
    with app.app_context():
        cycle_id = cycle_service.active_cycle()["id"]
    assert client.get(f"/ciclo/{cycle_id}/relatorio").status_code == 200


def test_taf_marca_atualiza_teste(client, app):
    with app.app_context():
        test_id = query_one("SELECT id FROM taf_tests ORDER BY id LIMIT 1")["id"]
    client.post(f"/taf/testes/{test_id}/marca",
                data={"date": today_iso(), "value": "2600"}, follow_redirects=True)
    with app.app_context():
        row = query_one("SELECT * FROM taf_tests WHERE id = ?", (test_id,))
        assert row["current_mark"] == 2600.0
        assert row["measured_at"] == today_iso()


def test_faculdade_registra_tempo(client, app):
    client.post("/faculdade/sessoes", data={"date": today_iso(), "minutes": "1h30"},
                follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT SUM(minutes) FROM college_sessions", (), 0) == 90


def test_pagina_inexistente_retorna_404(client):
    assert client.get("/pagina-que-nao-existe").status_code == 404
