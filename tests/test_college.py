"""Faculdade: plano ate o prazo e revisao espacada propria."""

from app.db import query_one
from app.services import college as college_service
from app.services import settings as settings_service
from app.utils import add_days, days_between, today_iso


def _pendentes(temas):
    return [t for t in temas if t["status"] != "concluido"]


# --------------------------------------------------------------------------
# Conteudo semeado
# --------------------------------------------------------------------------
def test_seed_cadastra_disciplinas_e_temas(ctx):
    nomes = {t["subject_name"] for t in college_service.topics()}
    assert "Banco de Dados NoSQL" in nomes
    assert "Linhas de Produtos de Software" in nomes
    nosql = [t for t in college_service.topics() if t["subject_name"] == "Banco de Dados NoSQL"]
    assert len(nosql) == 11


def test_tema_ja_estudado_entra_concluido_e_com_revisao_aberta(ctx):
    tema = query_one("SELECT * FROM college_topics WHERE name LIKE 'Tema 2 - Sintaxe%'")
    assert tema["status"] == "concluido"
    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))
    assert revisao["status"] == "pendente"
    assert revisao["next_date"] == add_days(today_iso(), 1)


# --------------------------------------------------------------------------
# Plano ate o prazo
# --------------------------------------------------------------------------
def test_plano_cabe_dentro_do_prazo(ctx):
    plano = college_service.plan()
    prazo = college_service.deadline()
    assert plano
    assert plano[0]["planned_date"] == today_iso()
    assert all(t["planned_date"] <= prazo for t in plano)
    datas = [t["planned_date"] for t in plano]
    assert datas == sorted(datas)


def test_plano_alterna_disciplinas(ctx):
    """Duas disciplinas iguais seguidas so quando nao ha outra opcao."""
    plano = college_service.plan()
    seguidas = [1 for a, b in zip(plano, plano[1:])
                if a["college_subject_id"] == b["college_subject_id"]]
    assert not seguidas


def test_escolher_o_tema_de_hoje_fura_a_fila(ctx):
    plano = college_service.plan()
    outro = plano[3]

    college_service.set_focus(outro["id"])

    depois = college_service.plan()
    assert depois[0]["id"] == outro["id"]
    assert depois[0]["planned_date"] == today_iso()
    assert depois[0]["chosen"] is True
    assert len(depois) == len(plano)      # nada some, a fila so anda uma casa


def test_escolha_do_dia_vence_no_dia_seguinte(ctx):
    outro = college_service.plan()[3]
    college_service.set_focus(outro["id"])

    amanha = college_service.plan(add_days(today_iso(), 1))
    assert amanha[0]["id"] != outro["id"]


def test_concluir_o_tema_escolhido_limpa_a_escolha(ctx):
    outro = college_service.plan()[3]
    college_service.set_focus(outro["id"])
    college_service.complete_topic(outro["id"])
    assert college_service.focus() is None


def test_concluir_tema_abre_revisao_e_refaz_o_plano(ctx):
    plano = college_service.plan()
    tema = plano[0]
    total_antes = len(plano)

    college_service.complete_topic(tema["id"])

    depois = college_service.plan()
    assert len(depois) == total_antes - 1
    assert tema["id"] not in [t["id"] for t in depois]

    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))
    assert revisao["next_date"] == add_days(today_iso(), 1)


def test_atraso_nao_gera_pendencia_o_plano_e_redistribuido(ctx):
    """Nao estudar hoje nao acumula: os temas que sobraram ganham o tempo que sobrou."""
    antes = college_service.plan()
    depois = college_service.plan(add_days(today_iso(), 10))
    assert len(antes) == len(depois)
    assert depois[0]["planned_date"] == add_days(today_iso(), 10)
    assert all(t["planned_date"] <= college_service.deadline() for t in depois)


def test_prazo_apertado_empilha_temas_no_mesmo_dia_em_vez_de_estourar(ctx):
    settings_service.set_value("college_deadline", add_days(today_iso(), 3))
    plano = college_service.plan()
    assert all(days_between(today_iso(), t["planned_date"]) <= 3 for t in plano)
    assert college_service.progress()["tight"] is True


def test_progresso_conta_temas_e_ritmo(ctx):
    progresso = college_service.progress()
    assert progresso["total"] == progresso["done"] + progresso["pending"]
    assert progresso["done"] == 4       # os temas ja estudados do seed
    assert progresso["per_week"] > 0
    assert progresso["late"] is False


def test_reabrir_tema_devolve_ao_plano_e_arquiva_a_revisao(ctx):
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    college_service.reopen_topic(tema["id"])

    assert tema["id"] in [t["id"] for t in college_service.plan()]
    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))
    assert revisao["status"] == "arquivada"


# --------------------------------------------------------------------------
# Revisao espacada
# --------------------------------------------------------------------------
def test_revisao_segue_a_lista_de_intervalos(ctx):
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))

    resultado = college_service.complete_review(revisao["id"])
    assert resultado["interval_days"] == 7       # padrao da faculdade: 1,7,15,30
    assert resultado["next_date"] == add_days(today_iso(), 7)


def test_proxima_revisao_sai_da_data_real_da_conclusao(ctx):
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))

    atrasado = add_days(today_iso(), 5)
    resultado = college_service.complete_review(revisao["id"], done_date=atrasado)
    assert resultado["next_date"] == add_days(atrasado, 7)


def test_sequencia_termina_e_consolida(ctx):
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    revisao = query_one("SELECT * FROM college_reviews WHERE college_topic_id = ?",
                        (tema["id"],))
    for _ in range(len(college_service.intervals()) - 1):
        assert college_service.complete_review(revisao["id"])["finished"] is False
    final = college_service.complete_review(revisao["id"])
    assert final["finished"] is True
    assert query_one("SELECT status FROM college_reviews WHERE id = ?",
                     (revisao["id"],))["status"] == "concluida"


def test_concluir_tema_duas_vezes_nao_duplica_fila(ctx):
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    college_service.complete_topic(tema["id"])
    total = query_one("SELECT COUNT(*) AS n FROM college_reviews WHERE college_topic_id = ?",
                      (tema["id"],))["n"]
    assert total == 1


def test_fila_da_faculdade_nao_entra_na_fila_do_prf(ctx):
    from app.services import reviews as reviews_service

    antes = reviews_service.counts()["total"]
    tema = college_service.plan()[0]
    college_service.complete_topic(tema["id"])
    assert reviews_service.counts()["total"] == antes


# --------------------------------------------------------------------------
# Telas
# --------------------------------------------------------------------------
def test_tela_da_faculdade_mostra_tema_da_vez_e_prazo(client):
    resposta = client.get("/faculdade/")
    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Estude agora" in corpo
    assert "Plano ate o prazo" in corpo
    assert "Revisoes de hoje" in corpo


def test_concluir_tema_pela_tela(client, app):
    with app.app_context():
        tema = college_service.plan()[0]
    resposta = client.post(f"/faculdade/temas/{tema['id']}/concluir",
                           data={"minutes": "60"}, follow_redirects=True)
    assert resposta.status_code == 200
    with app.app_context():
        assert college_service.get_topic(tema["id"])["status"] == "concluido"
        assert college_service.minutes_of_topic(tema["id"]) == 60


def test_escolher_tema_de_hoje_pela_tela(client, app):
    with app.app_context():
        outro = college_service.plan()[3]
    resposta = client.post(f"/faculdade/temas/{outro['id']}/hoje", follow_redirects=True)
    assert resposta.status_code == 200
    with app.app_context():
        assert college_service.plan()[0]["id"] == outro["id"]


def test_prazo_salvo_nas_configuracoes_refaz_o_plano(client, app):
    client.post("/configuracoes/salvar", data={"college_deadline": add_days(today_iso(), 20)},
                follow_redirects=True)
    with app.app_context():
        assert college_service.deadline() == add_days(today_iso(), 20)
        assert all(t["planned_date"] <= add_days(today_iso(), 20)
                   for t in college_service.plan())
