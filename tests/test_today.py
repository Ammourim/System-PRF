"""O ciclo sequencial e a aba HOJE.

Regras fixadas aqui:
  * a aba HOJE mostra UMA disciplina - a da vez;
  * abrir o formulario de estudo NAO avanca o ciclo;
  * concluir o estudo avanca, e a proxima aparece na hora;
  * frequencia define quantas vezes a disciplina entra na sequencia;
  * prioridade define a ordem, nunca a quantidade;
  * inativa nao entra;
  * revisao espacada e independente do ciclo;
  * um dia sem estudar nao mexe na posicao.
"""

from app.db import query_one, scalar
from app.services import reviews as reviews_service
from app.services import today as today_service
from app.utils import add_days, today_iso

# Configuracao pedida: CTB 3x, Portugues 2x, as demais ativas 1x, quatro inativas.
ATIVAS = ["CTB", "Portugues", "Administrativo", "Constitucional", "Informatica",
          "RLM", "Leg. Especial", "Etica", "Penal", "Processo Penal"]
INATIVAS = ["Espanhol", "Dir. Humanos", "Geopolitica", "Fisica"]


def _sequencia_curta(ctx):
    """Ciclo minimo e previsivel: CTB (2x) e Portugues (1x), o resto fora."""
    ctx.execute("UPDATE disciplines SET active = 0")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'maxima', frequency = 2"
                " WHERE short_name = 'CTB'")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'alta', frequency = 1"
                " WHERE short_name = 'Portugues'")
    ctx.commit()


# --------------------------------------------------------------------------
# Configuracao inicial das disciplinas (migration 005)
# --------------------------------------------------------------------------
def test_prioridades_iniciais(ctx):
    def prioridade(short):
        return query_one("SELECT priority FROM disciplines WHERE short_name = ?",
                         (short,))["priority"]

    assert prioridade("CTB") == "maxima"
    assert prioridade("Portugues") == "maxima"
    for short in ["Administrativo", "Constitucional", "Informatica", "RLM",
                  "Leg. Especial", "Etica"]:
        assert prioridade(short) == "alta", short
    assert prioridade("Penal") == "media"
    assert prioridade("Processo Penal") == "media"


def test_quatro_disciplinas_ficam_inativas_mas_cadastradas(ctx):
    for short in INATIVAS:
        row = query_one("SELECT active FROM disciplines WHERE short_name = ?", (short,))
        assert row is not None, f"{short} nao pode ser excluida"
        assert row["active"] == 0, f"{short} deveria estar inativa"


def test_frequencias_iniciais(ctx):
    def frequencia(short):
        return query_one("SELECT frequency FROM disciplines WHERE short_name = ?",
                         (short,))["frequency"]

    assert frequencia("CTB") == 3
    assert frequencia("Portugues") == 2
    for short in ATIVAS[2:]:
        assert frequencia(short) == 1, short


# --------------------------------------------------------------------------
# Montagem da sequencia
# --------------------------------------------------------------------------
def test_cada_disciplina_aparece_conforme_a_frequencia(ctx):
    nomes = [d["short_name"] for d in today_service.sequence()]
    assert nomes.count("CTB") == 3
    assert nomes.count("Portugues") == 2
    for short in ATIVAS[2:]:
        assert nomes.count(short) == 1, short
    assert len(nomes) == 13  # 3 + 2 + (8 x 1)


def test_disciplina_inativa_nao_entra_no_ciclo(ctx):
    nomes = [d["short_name"] for d in today_service.sequence()]
    for short in INATIVAS:
        assert short not in nomes


def test_prioridade_ordena_mas_nao_multiplica(ctx):
    """Prioridade maxima com frequencia 1 aparece uma vez so - antes das outras."""
    ctx.execute("UPDATE disciplines SET active = 0")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'maxima', frequency = 1"
                " WHERE short_name = 'CTB'")
    ctx.execute("UPDATE disciplines SET active = 1, priority = 'baixa', frequency = 1"
                " WHERE short_name = 'Penal'")
    ctx.commit()

    nomes = [d["short_name"] for d in today_service.sequence()]
    assert nomes == ["CTB", "Penal"]


def test_repeticoes_ficam_espalhadas(ctx):
    """CTB 3x nao pode sair como CTB, CTB, CTB no comeco."""
    nomes = [d["short_name"] for d in today_service.sequence()]
    posicoes = [i for i, nome in enumerate(nomes) if nome == "CTB"]
    for anterior, seguinte in zip(posicoes, posicoes[1:]):
        assert seguinte - anterior > 1, nomes
    # e a volta do ciclo tambem nao pode emendar duas iguais
    assert nomes[0] != nomes[-1], nomes


def test_ciclo_sem_disciplina_ativa(ctx):
    ctx.execute("UPDATE disciplines SET active = 0")
    ctx.commit()
    assert today_service.sequence() == []
    assert today_service.current() is None


# --------------------------------------------------------------------------
# Posicao e avanco
# --------------------------------------------------------------------------
def test_hoje_mostra_uma_disciplina_so(client, ctx):
    corpo = client.get("/").get_data(as_text=True)
    atual = today_service.current()

    assert "Proximo estudo" in corpo
    assert atual["name"] in corpo
    # Um unico botao Estudar: a tela nao e uma lista de disciplinas.
    assert corpo.count(">Estudar</a>") == 1
    assert corpo.count("/estudar?discipline_id=") == 1


def test_abrir_o_formulario_nao_avanca(client, ctx):
    antes = today_service.position()
    atual = today_service.current()

    for _ in range(3):
        assert client.get(f"/estudar?discipline_id={atual['id']}").status_code == 200
        client.get("/")

    assert today_service.position() == antes
    assert today_service.current()["id"] == atual["id"]


def test_concluir_estudo_avanca_para_a_proxima(client, ctx):
    _sequencia_curta(ctx)
    assert [d["short_name"] for d in today_service.sequence()] == ["CTB", "Portugues", "CTB"]

    primeira = today_service.current()
    assert primeira["short_name"] == "CTB"

    client.post("/estudar", data={"discipline_id": str(primeira["id"]),
                                  "subject_name": "Infracoes"}, follow_redirects=True)
    assert today_service.current()["short_name"] == "Portugues"

    client.post("/estudar", data={"discipline_id": str(today_service.current()["id"]),
                                  "subject_name": "Crase"}, follow_redirects=True)
    assert today_service.current()["short_name"] == "CTB"


def test_a_proxima_aparece_na_tela_imediatamente(client, ctx):
    _sequencia_curta(ctx)
    atual = today_service.current()
    resposta = client.post("/estudar", data={"discipline_id": str(atual["id"]),
                                             "subject_name": "Infracoes"},
                           follow_redirects=True)
    corpo = resposta.get_data(as_text=True)
    assert "Lingua Portuguesa" in corpo


def test_ciclo_da_a_volta(client, ctx):
    _sequencia_curta(ctx)
    vistos = []
    for _ in range(4):
        atual = today_service.current()
        vistos.append(atual["short_name"])
        client.post("/estudar", data={"discipline_id": str(atual["id"]),
                                      "subject_name": "Assunto"}, follow_redirects=True)
    assert vistos == ["CTB", "Portugues", "CTB", "CTB"]  # volta ao inicio


def test_nao_estudar_nao_mexe_na_posicao(client, ctx):
    atual = today_service.current()
    for _ in range(5):
        assert client.get("/").status_code == 200
    assert today_service.current()["id"] == atual["id"]


def test_posicao_sobrevive_a_mudanca_de_configuracao(client, ctx):
    """Desativar uma disciplina encurta a sequencia sem estourar a posicao."""
    for _ in range(9):
        atual = today_service.current()
        client.post("/estudar", data={"discipline_id": str(atual["id"]),
                                      "subject_name": "X"}, follow_redirects=True)

    ctx.execute("UPDATE disciplines SET active = 0 WHERE short_name IN ('Penal', 'Etica')")
    ctx.commit()

    atual = today_service.current()
    assert atual is not None
    assert 1 <= atual["position"] <= len(today_service.sequence())


def test_reiniciar_ciclo_nao_apaga_nada(client, ctx):
    atual = today_service.current()
    client.post("/estudar", data={"discipline_id": str(atual["id"]),
                                  "subject_name": "Infracoes", "questions_total": "10",
                                  "questions_correct": "7"}, follow_redirects=True)

    client.post("/disciplinas/ciclo/reiniciar", follow_redirects=True)

    assert today_service.position() == 0
    assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 1
    assert scalar("SELECT COUNT(*) FROM questions", (), 0) == 1
    assert scalar("SELECT COUNT(*) FROM subjects WHERE name = 'Infracoes'", (), 0) == 1


# --------------------------------------------------------------------------
# Registro de estudo
# --------------------------------------------------------------------------
def test_assunto_e_texto_livre_e_nao_duplica(client, ctx):
    for _ in range(3):
        client.post("/estudar", data={"discipline_id": "1", "subject_name": "Infracoes"},
                    follow_redirects=True)
    assert scalar("SELECT COUNT(*) FROM subjects WHERE lower(name) = 'infracoes'", (), 0) == 1
    assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 3


def test_estudo_sem_tempo_e_aceito(client, ctx):
    client.post("/estudar", data={"discipline_id": "1", "subject_name": "Sinalizacao"},
                follow_redirects=True)
    row = query_one("SELECT * FROM study_sessions ORDER BY id DESC LIMIT 1")
    assert row["actual_minutes"] == 0 and row["subject_id"] is not None


def test_questoes_sao_registradas_sem_mexer_no_ciclo(client, ctx):
    """Questoes entram no historico; o ciclo anda uma casa - nem mais, nem menos."""
    antes = today_service.position()
    client.post("/estudar", data={
        "discipline_id": str(today_service.current()["id"]), "subject_name": "Placas",
        "questions_total": "20", "questions_correct": "16",
    }, follow_redirects=True)

    row = query_one("SELECT * FROM questions ORDER BY id DESC LIMIT 1")
    assert row["total"] == 20 and row["correct"] == 16 and row["percentage"] == 80.0
    assert today_service.position() == (antes + 1) % len(today_service.sequence())


def test_registrar_estudo_nao_gera_revisao(client, ctx):
    client.post("/estudar", data={"discipline_id": "1", "subject_name": "Infracoes",
                                  "questions_total": "10", "questions_correct": "9"},
                follow_redirects=True)
    subject = query_one("SELECT * FROM subjects WHERE name = 'Infracoes'")
    assert subject["status"] == "em_andamento" and subject["completed_at"] is None
    assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0


# --------------------------------------------------------------------------
# Conclusao do assunto e revisao (independentes do ciclo)
# --------------------------------------------------------------------------
def _assunto(client, name="Infracoes"):
    client.post("/estudar", data={"discipline_id": "1", "subject_name": name},
                follow_redirects=True)
    return query_one("SELECT id FROM subjects WHERE name = ?", (name,))["id"]


def test_assunto_concluido_pode_gerar_revisao(client, ctx):
    subject_id = _assunto(client)
    resposta = client.post(f"/assunto/{subject_id}/concluir", follow_redirects=True)
    assert "Deseja agendar as revisoes espacadas?" in resposta.get_data(as_text=True)
    assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0  # ainda nao respondeu

    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "1"},
                follow_redirects=True)
    review = query_one("SELECT * FROM reviews ORDER BY id DESC LIMIT 1")
    assert review["subject_id"] == subject_id
    assert review["interval_days"] == 1
    assert review["next_date"] == add_days(today_iso(), 1)


def test_responder_nao_nao_cria_revisao(client, ctx):
    subject_id = _assunto(client)
    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "0"},
                follow_redirects=True)
    assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 0


def test_concluir_duas_vezes_nao_duplica_revisao(client, ctx):
    subject_id = _assunto(client)
    for _ in range(3):
        client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "1"},
                    follow_redirects=True)
    assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 1


def test_reabrir_assunto_volta_para_em_andamento(client, ctx):
    subject_id = _assunto(client)
    client.post(f"/assunto/{subject_id}/concluir", data={"agendar": "0"},
                follow_redirects=True)
    client.post(f"/assunto/{subject_id}/reabrir", follow_redirects=True)
    row = query_one("SELECT * FROM subjects WHERE id = ?", (subject_id,))
    assert row["status"] == "em_andamento" and row["completed_at"] is None


def test_concluir_revisao_nao_mexe_na_posicao_do_ciclo(client, ctx):
    """Revisao e ciclo sao independentes: uma nao mexe na outra."""
    review_id = reviews_service.create_review(discipline_id=1, title="Crase")
    ctx.execute("UPDATE reviews SET next_date = ? WHERE id = ?", (today_iso(), review_id))
    ctx.commit()

    antes = today_service.position()
    atual = today_service.current()

    corpo = client.get("/").get_data(as_text=True)
    assert "Crase" in corpo                      # a revisao aparece
    assert atual["name"] in corpo                # e o ciclo continua onde estava

    client.post(f"/revisoes/{review_id}/concluir", follow_redirects=True)

    assert today_service.position() == antes
    assert today_service.current()["id"] == atual["id"]
    assert query_one("SELECT interval_days FROM reviews WHERE id = ?",
                     (review_id,))["interval_days"] == 7
