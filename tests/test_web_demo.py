"""As mesmas telas, agora com dados de demonstracao carregados.

Sem dados, muitos ramos de template (graficos, listas, badges) nunca executam.
"""

from app.db import get_db, query_all
from app.seed import seed_demo


def _all_pages(client, app):
    urls = ["/", "/ciclo/", "/ciclo/montar", "/sessoes/", "/sessoes/nova", "/questoes/",
            "/revisoes/", "/erros/", "/simulados/", "/simulados/cronometro", "/desempenho/",
            "/desempenho/ajustes", "/disciplinas/", "/taf/", "/taf/treinos/", "/faculdade/",
            "/configuracoes/", "/dados/"]
    with app.app_context():
        for row in query_all("SELECT id FROM disciplines LIMIT 3"):
            urls.append(f"/disciplinas/{row['id']}")
        for row in query_all("SELECT id FROM mock_exams"):
            urls.append(f"/simulados/{row['id']}")
        for row in query_all("SELECT id FROM study_cycles"):
            urls.append(f"/ciclo/{row['id']}/relatorio")
        for row in query_all("SELECT id FROM study_sessions LIMIT 3"):
            urls.append(f"/sessoes/{row['id']}/editar")
        for row in query_all("SELECT id FROM questions LIMIT 3"):
            urls.append(f"/questoes/{row['id']}")
        for row in query_all("SELECT id FROM taf_workouts"):
            urls.append(f"/taf/treinos/{row['id']}")
        for row in query_all("SELECT id FROM taf_workout_exercises LIMIT 3"):
            urls.append(f"/taf/treinos/exercicios/{row['id']}/editar")
        for row in query_all("SELECT id FROM taf_workout_sessions"):
            urls.append(f"/taf/treinos/execucao/{row['id']}/resumo")
        for row in query_all("SELECT id FROM taf_workouts LIMIT 1"):
            urls.append(f"/taf/treinos/{row['id']}/exercicios/novo")
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, f"{url} retornou {response.status_code}"


def test_paginas_com_dados_de_demonstracao(client, app):
    with app.app_context():
        seed_demo(get_db())
    _all_pages(client, app)


def test_banner_de_demo_aparece_e_some(client, app):
    with app.app_context():
        seed_demo(get_db())
    assert "Demonstracao" in client.get("/").get_data(as_text=True)

    client.post("/configuracoes/demo", data={"action": "clear"}, follow_redirects=True)
    assert "Demonstracao" not in client.get("/").get_data(as_text=True)
    _all_pages(client, app)


def test_desempenho_em_varios_periodos(client, app):
    with app.app_context():
        seed_demo(get_db())
    for days in [7, 14, 30, 60, 90, 180]:
        assert client.get(f"/desempenho/?days={days}").status_code == 200
        assert client.get(f"/desempenho/ajustes?days={days}").status_code == 200


def test_filtros_das_listagens(client, app):
    with app.app_context():
        seed_demo(get_db())
    urls = [
        "/sessoes/?discipline_id=1&type=questoes&start=2020-01-01&end=2030-01-01",
        "/questoes/?discipline_id=1&banca=Cebraspe&only_wrong=1&max_pct=70",
        "/erros/?discipline_id=1&category=C&status=aberto",
        "/erros/?all=1",
        "/revisoes/?days=30",
        "/taf/treinos/",
        "/taf/treinos/historico",
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url
