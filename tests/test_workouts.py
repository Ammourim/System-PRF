"""Treinos: plano, prescricao, execucao e historico."""

from app.db import query_all, query_one, scalar
from app.services import workouts as service
from app.utils import today_iso


def _plano(nome="Treino de Forca A", **campos):
    return service.create_workout(nome, objective="Forca de membros superiores",
                                  type="forca", duration_minutes=30, **campos)


def _barra(workout_id):
    return service.add_exercise(workout_id, "Barra fixa", category="calistenia",
                                sets=4, reps=6, rest_seconds=90, goal="24 repeticoes")


# ---------------------------------------------------------------- plano
def test_criar_plano_e_exercicios(ctx):
    workout_id = _plano()
    plano = service.get_workout(workout_id)
    assert plano["name"] == "Treino de Forca A"
    assert plano["status"] == "ativo"
    assert service.exercises(workout_id) == []

    _barra(workout_id)
    service.add_exercise(workout_id, "Corrida", category="corrida", sets=1,
                         distance_km=5.0, total_seconds=1800)
    itens = service.exercises(workout_id)
    assert [e["name"] for e in itens] == ["Barra fixa", "Corrida"]
    assert [e["position"] for e in itens] == [1, 2]


def test_prescricao_aceita_campos_diferentes_por_exercicio(ctx):
    """Cada tipo usa os campos que fazem sentido; o resto fica nulo."""
    workout_id = _plano()
    barra = service.get_exercise(_barra(workout_id))
    prancha = service.get_exercise(service.add_exercise(
        workout_id, "Prancha", category="core", sets=4, seconds_per_set=45,
        rest_seconds=30))

    assert barra["reps"] == 6 and barra["seconds_per_set"] is None
    assert prancha["seconds_per_set"] == 45 and prancha["reps"] is None
    assert "6 rep" in service.describe_prescription(barra)
    assert "45s por serie" in service.describe_prescription(prancha)


def test_reordenar_duplicar_e_excluir(ctx):
    workout_id = _plano()
    a = service.add_exercise(workout_id, "A")
    b = service.add_exercise(workout_id, "B")
    service.add_exercise(workout_id, "C")

    service.move_exercise(b, -1)
    assert [e["name"] for e in service.exercises(workout_id)] == ["B", "A", "C"]

    service.move_exercise(b, -1)  # ja e o primeiro: nao faz nada
    assert [e["name"] for e in service.exercises(workout_id)] == ["B", "A", "C"]

    copia = service.duplicate_exercise(a)
    assert service.get_exercise(copia)["name"] == "A (copia)"
    assert len(service.exercises(workout_id)) == 4

    service.delete_exercise(copia)
    # Posicoes ficam sem buracos depois da exclusao.
    assert [e["position"] for e in service.exercises(workout_id)] == [1, 2, 3]


def test_vigencia_define_treino_do_dia(ctx):
    dentro = _plano("Vigente", start_date="2026-01-01", end_date="2030-01-01")
    _plano("Vencido", start_date="2020-01-01", end_date="2020-12-31")
    aberto = _plano("Sem fim", start_date="2020-01-01", end_date=None)

    ativos = [w["id"] for w in service.active_today("2026-08-15")]
    assert dentro in ativos and aberto in ativos
    assert len(ativos) == 2


# ------------------------------------------------------------- execucao
def test_execucao_copia_a_prescricao(ctx):
    """A sessao guarda uma copia: editar o plano depois nao reescreve o historico."""
    workout_id = _plano()
    exercise_id = _barra(workout_id)

    session_id = service.start_session(workout_id)
    copia = service.session_exercises(session_id)[0]
    assert copia["planned_sets"] == 4 and copia["planned_reps"] == 6

    service.update_exercise(exercise_id, "Barra fixa", sets=10, reps=99)
    copia = service.session_exercises(session_id)[0]
    assert copia["planned_sets"] == 4 and copia["planned_reps"] == 6


def test_nao_inicia_treino_sem_exercicio(ctx):
    assert service.start_session(_plano()) is None


def test_registrar_series_e_calcular_resultado(ctx):
    """Prescricao 4x6 = 24; realizado 6+6+5+4 = 21."""
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    item = service.session_exercises(session_id)[0]

    for numero, reps in enumerate([6, 6, 5, 4], start=1):
        service.log_set(item["id"], set_number=numero, reps=reps)

    progresso = service.exercise_progress(item)
    assert progresso["sets_done"] == 4
    assert progresso["target"] == 24
    assert progresso["achieved"] == 21
    assert progresso["unit"] == "rep"
    assert progresso["pct"] == 87.5


def test_corrigir_serie_nao_duplica(ctx):
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    item = service.session_exercises(session_id)[0]

    service.log_set(item["id"], set_number=1, reps=5)
    service.log_set(item["id"], set_number=1, reps=6)  # correcao
    series = service.session_sets(item["id"])
    assert len(series) == 1 and series[0]["reps"] == 6


def test_exercicio_atual_avanca_em_ordem(ctx):
    workout_id = _plano()
    _barra(workout_id)
    service.add_exercise(workout_id, "Corrida", sets=1, distance_km=5.0)
    session_id = service.start_session(workout_id)

    assert service.current_exercise(session_id)["name"] == "Barra fixa"
    service.set_exercise_status(service.current_exercise(session_id)["id"], "concluido")
    assert service.current_exercise(session_id)["name"] == "Corrida"
    service.set_exercise_status(service.current_exercise(session_id)["id"], "pulado")
    assert service.current_exercise(session_id) is None


def test_encerrar_marca_pendentes_como_pulados(ctx):
    workout_id = _plano()
    _barra(workout_id)
    service.add_exercise(workout_id, "Corrida", sets=1)
    session_id = service.start_session(workout_id)

    service.finish_session(session_id, minutes=40)
    sessao = service.get_session(session_id)
    assert sessao["status"] == "concluida" and sessao["duration_minutes"] == 40
    assert {e["status"] for e in service.session_exercises(session_id)} == {"pulado"}
    assert service.open_session() is None


def test_resumo_da_sessao(ctx):
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    item = service.session_exercises(session_id)[0]
    for numero in (1, 2):
        service.log_set(item["id"], set_number=numero, reps=6)

    resumo = service.session_summary(session_id)
    assert resumo["sets_planned"] == 4 and resumo["sets_done"] == 2
    assert resumo["pct"] == 50.0
    assert resumo["total_exercises"] == 1


# ------------------------------------------ preservacao do historico
def test_excluir_exercicio_preserva_execucoes(ctx):
    workout_id = _plano()
    exercise_id = _barra(workout_id)
    session_id = service.start_session(workout_id)
    item = service.session_exercises(session_id)[0]
    service.log_set(item["id"], set_number=1, reps=6)

    service.delete_exercise(exercise_id)

    assert service.exercises(workout_id) == []
    copia = service.session_exercises(session_id)[0]
    assert copia["name"] == "Barra fixa"          # o nome ficou na copia
    assert copia["workout_exercise_id"] is None   # so o vinculo se perdeu
    assert len(service.session_sets(copia["id"])) == 1


def test_excluir_plano_preserva_execucoes(ctx):
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    service.finish_session(session_id)

    service.delete_workout(workout_id)

    sessao = service.get_session(session_id)
    assert sessao is not None
    assert sessao["workout_id"] is None
    assert sessao["workout_name"] == "Treino de Forca A"
    assert scalar("SELECT COUNT(*) FROM taf_workout_exercises", (), 0) == 0


def test_excluir_sessao_apaga_series_em_cascata(ctx):
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    item = service.session_exercises(session_id)[0]
    service.log_set(item["id"], set_number=1, reps=6)

    service.delete_session(session_id)
    assert scalar("SELECT COUNT(*) FROM taf_session_exercises", (), 0) == 0
    assert scalar("SELECT COUNT(*) FROM taf_session_sets", (), 0) == 0


def test_contagem_e_minutos_no_periodo(ctx):
    workout_id = _plano()
    _barra(workout_id)
    session_id = service.start_session(workout_id)
    service.finish_session(session_id, minutes=45)

    hoje = today_iso()
    assert service.count_in_period(hoje, hoje) == 1
    assert service.minutes_in_period(hoje, hoje) == 45
    assert service.count_in_period("2000-01-01", "2000-01-02") == 0


# ------------------------------------------------------------- rotas HTTP
def test_fluxo_completo_pelas_rotas(client, app):
    resposta = client.post("/taf/treinos/salvar", data={
        "name": "Treino de Forca A",
        "objective": "Desenvolver forca para o TAF",
        "type": "forca", "duration_minutes": "30",
        "start_date": today_iso(), "notes": "Priorizar execucao correta.",
    })
    assert resposta.status_code == 302
    with app.app_context():
        plano = query_one("SELECT * FROM taf_workouts ORDER BY id DESC LIMIT 1")
        workout_id = plano["id"]
        assert plano["objective"] == "Desenvolver forca para o TAF"
    # Cadastrar leva direto para a pagina do treino.
    assert f"/taf/treinos/{workout_id}" in resposta.headers["Location"]

    client.post(f"/taf/treinos/{workout_id}/exercicios/salvar", data={
        "name": "Barra fixa", "category": "calistenia", "sets": "4", "reps": "6",
        "rest_seconds": "90", "goal": "24 repeticoes",
    }, follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM taf_workout_exercises", (), 0) == 1

    client.post(f"/taf/treinos/{workout_id}/iniciar", follow_redirects=True)
    with app.app_context():
        sessao = query_one("SELECT * FROM taf_workout_sessions ORDER BY id DESC LIMIT 1")
        session_id = sessao["id"]
        assert sessao["status"] == "em_andamento"
        item = query_all("SELECT * FROM taf_session_exercises WHERE session_id = ?",
                         (session_id,))[0]

    for numero, reps in enumerate([6, 6, 5, 4], start=1):
        client.post(f"/taf/treinos/execucao/{session_id}/serie", data={
            "session_exercise_id": str(item["id"]), "set_number": str(numero),
            "reps": str(reps),
        }, follow_redirects=True)

    with app.app_context():
        # Bateu as 4 series previstas: o exercicio fecha sozinho.
        assert query_one("SELECT status FROM taf_session_exercises WHERE id = ?",
                         (item["id"],))["status"] == "concluido"
        assert scalar("SELECT SUM(reps) FROM taf_session_sets", (), 0) == 21

    client.post(f"/taf/treinos/execucao/{session_id}/encerrar",
                data={"status": "concluida", "duration_minutes": "35"},
                follow_redirects=True)
    with app.app_context():
        sessao = query_one("SELECT * FROM taf_workout_sessions WHERE id = ?", (session_id,))
        assert sessao["status"] == "concluida" and sessao["duration_minutes"] == 35

    assert client.get(f"/taf/treinos/execucao/{session_id}/resumo").status_code == 200
    assert client.get("/taf/treinos/historico").status_code == 200


def test_tempo_aceita_segundos_e_minuto_segundo(client, app):
    """'45' = 45s e '1:30' = 90s. Ler 1:30 como 90 minutos seria 60x errado."""
    with app.app_context():
        workout_id = _plano("Treino de tempo")

    client.post(f"/taf/treinos/{workout_id}/exercicios/salvar", data={
        "name": "Prancha", "category": "core", "sets": "4",
        "seconds_per_set": "45", "rest_seconds": "1:30",
    }, follow_redirects=True)

    with app.app_context():
        item = query_one("SELECT * FROM taf_workout_exercises ORDER BY id DESC LIMIT 1")
        assert item["seconds_per_set"] == 45
        assert item["rest_seconds"] == 90


def test_campos_vazios_ficam_nulos(client, app):
    """Nao obrigar todos os campos: o que nao for preenchido nao vira zero."""
    with app.app_context():
        workout_id = _plano("Treino minimo")

    client.post(f"/taf/treinos/{workout_id}/exercicios/salvar", data={
        "name": "Corrida livre", "category": "corrida", "sets": "", "reps": "",
        "seconds_per_set": "", "distance_km": "", "total_minutes": "", "rest_seconds": "",
    }, follow_redirects=True)

    with app.app_context():
        item = query_one("SELECT * FROM taf_workout_exercises ORDER BY id DESC LIMIT 1")
        assert item["name"] == "Corrida livre"
        for campo in ("sets", "reps", "seconds_per_set", "distance_km",
                      "total_seconds", "rest_seconds"):
            assert item[campo] is None, campo


def test_treino_sem_nome_e_rejeitado(client, app):
    client.post("/taf/treinos/salvar", data={"name": ""}, follow_redirects=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM taf_workouts", (), 0) == 0


def test_um_treino_em_andamento_por_vez(client, app):
    with app.app_context():
        primeiro = _plano("Treino A")
        _barra(primeiro)
        segundo = _plano("Treino B")
        _barra(segundo)

    client.post(f"/taf/treinos/{primeiro}/iniciar", follow_redirects=True)
    resposta = client.post(f"/taf/treinos/{segundo}/iniciar", follow_redirects=True)
    assert "Ja existe um treino em andamento" in resposta.get_data(as_text=True)
    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM taf_workout_sessions", (), 0) == 1


def test_iniciar_sem_exercicio_avisa(client, app):
    with app.app_context():
        workout_id = _plano("Treino vazio")
    resposta = client.post(f"/taf/treinos/{workout_id}/iniciar", follow_redirects=True)
    assert "Cadastre pelo menos um exercicio" in resposta.get_data(as_text=True)


def test_pagina_de_treino_inexistente_nao_quebra(client):
    assert client.get("/taf/treinos/9999", follow_redirects=True).status_code == 200
