"""Prioridade com efeito real na montagem do ciclo.

Cada teste aqui corresponde a um problema apontado na auditoria
(SYSTEM_CONTEXT.md, secoes 5.2, 5.8 e 6): prioridade era campo morto, a ordem
saia do numero de blocos e o arredondamento distorcia as metas em silencio.
"""

from app.db import query_all, query_one, scalar
from app.services import adaptive
from app.services import cycle as cycle_service
from app.utils import today_iso


def _plan(ctx=None, goal=1800):
    rows = query_all("SELECT * FROM disciplines")
    return cycle_service.generate_cycle_plan(rows, goal_minutes=goal,
                                             config=cycle_service.block_config())


def _names(sequence):
    return [b["short_name"] or b["name"] for b in sequence]


# --------------------------------------------------------------------------
# 1 e 2: ordem vem da prioridade, nao da quantidade de blocos
# --------------------------------------------------------------------------
def test_espanhol_nao_aparece_no_inicio_do_ciclo(ctx):
    """O bug original: Espanhol na posicao 3 por ter 2 blocos (auditoria, secao 6)."""
    sequence = _names(_plan(ctx)["sequence"])
    posicao = sequence.index("Espanhol") + 1

    assert posicao > 3
    # Tem de vir depois de todas as disciplinas de prioridade maxima/alta/media.
    prioritarias = ["CTB", "Portugues", "Administrativo", "Constitucional",
                    "Informatica", "RLM", "Leg. Especial", "Etica", "Penal",
                    "Processo Penal"]
    assert all(sequence.index(nome) < posicao - 1 for nome in prioritarias)


def test_prioridade_define_a_ordem_mesmo_com_menos_blocos(ctx):
    """Prioridade maxima com 1 bloco vem antes de prioridade baixa com 5 blocos."""
    plan = [
        {"discipline_id": 1, "name": "Baixa", "priority": "baixa", "incidence": 30,
         "block_list": [60, 60, 60, 60, 60]},
        {"discipline_id": 2, "name": "Maxima", "priority": "maxima", "incidence": 1,
         "block_list": [90]},
    ]
    ordered = [b["name"] for b in cycle_service.spread(plan)]
    assert ordered[0] == "Maxima"


def test_incidencia_sozinha_nao_furra_a_fila_da_prioridade(ctx):
    """Espanhol tem incidencia maior que Administrativo, mas prioridade menor."""
    espanhol = query_one("SELECT * FROM disciplines WHERE short_name = 'Espanhol'")
    administrativo = query_one("SELECT * FROM disciplines WHERE short_name = 'Administrativo'")
    assert espanhol["incidence"] > administrativo["incidence"]

    sequence = _names(_plan(ctx)["sequence"])
    assert sequence.index("Administrativo") < sequence.index("Espanhol")

    # A incidencia continua valendo DENTRO da mesma prioridade.
    plan = [
        {"discipline_id": 1, "name": "MenosIncidente", "priority": "alta", "incidence": 4,
         "block_list": [60]},
        {"discipline_id": 2, "name": "MaisIncidente", "priority": "alta", "incidence": 20,
         "block_list": [60]},
    ]
    assert [b["name"] for b in cycle_service.spread(plan)][0] == "MaisIncidente"


# --------------------------------------------------------------------------
# 3 e 4: meta do ciclo e meta de cada disciplina
# --------------------------------------------------------------------------
def test_meta_de_30h_nao_estoura_sem_aviso(ctx):
    """Antes: plano de 1875 min contra meta de 1800 e nenhum aviso."""
    result = _plan(ctx, goal=1800)
    assert result["total_minutes"] == 1800
    assert result["diff"] == 0
    assert result["within_tolerance"] is True
    assert result["warnings"] == []

    # Estourar a meta de proposito tem de gerar aviso explicito.
    ctx.execute("UPDATE disciplines SET target_minutes = 900 WHERE short_name = 'CTB'")
    ctx.commit()
    estourado = _plan(ctx, goal=1800)
    assert estourado["total_minutes"] > 1800
    assert estourado["within_tolerance"] is False
    assert any("meta de" in w for w in estourado["warnings"])


def test_meta_da_disciplina_nao_e_distorcida_em_silencio(ctx):
    """Antes: meta 120 com bloco 90 virava 90 min (-25%) sem nenhum aviso."""
    # O caso exato da auditoria.
    assert sum(cycle_service.blocks_for_target(120, 90)) == 120
    assert sum(cycle_service.blocks_for_target(90, 60)) == 90
    assert sum(cycle_service.blocks_for_target(60, 45)) == 60
    assert sum(cycle_service.blocks_for_target(105, 60)) == 105

    # Nenhum bloco maior que o tamanho preferido e nenhum minuto perdido.
    for target, block in [(120, 90), (90, 60), (60, 45), (450, 90), (270, 90)]:
        blocks = cycle_service.blocks_for_target(target, block)
        assert sum(blocks) == target
        assert max(blocks) <= block

    result = _plan(ctx)
    assert result["adjusted"] == []
    assert all(i["diff"] == 0 for i in result["items"] if i["included"])


def test_divergencia_de_meta_e_reportada_quando_existe(ctx):
    """Quando nao da para fechar exato, o sistema mostra a diferenca em vez de esconder."""
    ctx.execute("UPDATE disciplines SET target_minutes = 20, block_minutes = 90,"
                " min_blocks = 0 WHERE short_name = 'Fisica'")
    ctx.commit()
    fisica = next(i for i in _plan(ctx)["items"] if i["short_name"] == "Fisica")
    assert fisica["planned_minutes"] == 20
    assert fisica["blocks"] == 1


# --------------------------------------------------------------------------
# 5, 6 e 7: controle manual
# --------------------------------------------------------------------------
def test_usuario_pode_alterar_a_prioridade(client, app):
    with app.app_context():
        row = query_one("SELECT * FROM disciplines WHERE short_name = 'Espanhol'")

    client.post(f"/disciplinas/{row['id']}/salvar", data={
        "name": row["name"], "short_name": row["short_name"],
        "incidence": row["incidence"], "priority": "maxima", "status": row["status"],
        "block_minutes": row["block_minutes"], "target_minutes": row["target_minutes"],
        "desired_blocks": 0, "min_blocks": row["min_blocks"], "active": "1",
    }, follow_redirects=True)

    with app.app_context():
        assert query_one("SELECT priority FROM disciplines WHERE id = ?",
                         (row["id"],))["priority"] == "maxima"
        # E a mudanca aparece na ordem do ciclo imediatamente.
        sequence = _names(_plan()["sequence"])
        assert sequence.index("Espanhol") < sequence.index("Administrativo")


def test_frequencia_fixa_vence_o_calculo_automatico(ctx):
    ctx.execute("UPDATE disciplines SET desired_blocks = 4 WHERE short_name = 'Espanhol'")
    ctx.commit()
    espanhol = next(i for i in _plan(ctx)["items"] if i["short_name"] == "Espanhol")
    assert espanhol["blocks"] == 4
    assert "manualmente" in espanhol["note"]


def test_contato_minimo_mantem_disciplina_no_ciclo_sem_meta(ctx):
    """Status 'nao iniciada' nao ganha prioridade automatica, mas nao e esquecida."""
    ctx.execute("UPDATE disciplines SET target_minutes = 0 WHERE short_name = 'Geopolitica'")
    ctx.commit()
    geo = next(i for i in _plan(ctx)["items"] if i["short_name"] == "Geopolitica")
    assert geo["min_blocks"] == 1
    assert geo["included"] is True
    assert geo["blocks"] == 1

    ctx.execute("UPDATE disciplines SET min_blocks = 0 WHERE short_name = 'Geopolitica'")
    ctx.commit()
    geo = next(i for i in _plan(ctx)["items"] if i["short_name"] == "Geopolitica")
    assert geo["included"] is False
    assert "fora deste ciclo" in geo["note"]


def test_usuario_pode_desativar_e_reativar_disciplina(client, app):
    with app.app_context():
        row = query_one("SELECT * FROM disciplines WHERE short_name = 'Espanhol'")

    base = {
        "name": row["name"], "short_name": row["short_name"],
        "incidence": row["incidence"], "priority": row["priority"],
        "status": row["status"], "block_minutes": row["block_minutes"],
        "target_minutes": row["target_minutes"], "desired_blocks": 0,
        "min_blocks": row["min_blocks"],
    }

    # Desativar: checkbox `active` ausente.
    client.post(f"/disciplinas/{row['id']}/salvar", data=base, follow_redirects=True)
    with app.app_context():
        assert query_one("SELECT active FROM disciplines WHERE id = ?",
                         (row["id"],))["active"] == 0
        # Continua cadastrada, apenas fora do ciclo.
        espanhol = next(i for i in _plan()["items"] if i["short_name"] == "Espanhol")
        assert espanhol["included"] is False
        assert "inativa" in espanhol["note"]
        assert "Espanhol" not in _names(_plan()["sequence"])

    # Reativar.
    client.post(f"/disciplinas/{row['id']}/salvar", data=dict(base, active="1"),
                follow_redirects=True)
    with app.app_context():
        assert query_one("SELECT active FROM disciplines WHERE id = ?",
                         (row["id"],))["active"] == 1
        assert "Espanhol" in _names(_plan()["sequence"])


# --------------------------------------------------------------------------
# 8, 9 e 10: o que NAO pode mudar
# --------------------------------------------------------------------------
def test_ciclo_continua_independente_do_calendario(ctx):
    """Nem a prioridade nem a data mexem em `current_position`."""
    cycle = cycle_service.active_cycle()
    posicao = cycle["current_position"]

    ctx.execute("UPDATE disciplines SET priority = 'baixa' WHERE short_name = 'CTB'")
    ctx.commit()
    _plan(ctx)  # so calcula; nao escreve nada

    assert cycle_service.active_cycle()["current_position"] == posicao
    assert scalar("SELECT COUNT(*) FROM cycle_blocks WHERE done = 1", (), 0) == 0
    # Nenhuma data foi gravada em bloco nenhum.
    assert scalar("SELECT COUNT(*) FROM cycle_blocks WHERE done_at IS NOT NULL", (), 0) == 0


def test_desempenho_gera_sugestao_e_nao_altera_o_ciclo(ctx):
    """Regra preservada: o adaptive sugere, o usuario aplica."""
    ctx.execute("UPDATE disciplines SET status = 'em_andamento' WHERE short_name = 'Espanhol'")
    ctx.execute("INSERT INTO questions (date, discipline_id, total, correct, wrong, percentage)"
                " SELECT ?, id, 40, 8, 32, 20.0 FROM disciplines WHERE short_name = 'Espanhol'",
                (today_iso(),))
    ctx.commit()

    antes = query_one("SELECT target_minutes, priority FROM disciplines"
                      " WHERE short_name = 'Espanhol'")
    blocos_antes = query_all("SELECT discipline_id FROM cycle_blocks ORDER BY position")

    sugestao = next(s for s in adaptive.suggestions(days=60) if s["short_name"] == "Espanhol")
    assert sugestao["direction"] == "aumentar"
    assert sugestao["delta"] > 0

    depois = query_one("SELECT target_minutes, priority FROM disciplines"
                       " WHERE short_name = 'Espanhol'")
    assert depois["target_minutes"] == antes["target_minutes"]
    assert depois["priority"] == antes["priority"]
    assert [b["discipline_id"] for b in query_all(
        "SELECT discipline_id FROM cycle_blocks ORDER BY position")] == \
        [b["discipline_id"] for b in blocos_antes]


def test_regerar_o_ciclo_respeita_a_nova_prioridade(ctx):
    cycle = cycle_service.active_cycle()
    cycle_service.rebuild_blocks(cycle["id"], _plan(ctx)["plan"])
    inicial = [b["short_name"] for b in cycle_service.blocks(cycle["id"])]
    assert inicial[0] == "CTB"

    ctx.execute("UPDATE disciplines SET priority = 'maxima' WHERE short_name = 'Fisica'")
    ctx.execute("UPDATE disciplines SET priority = 'baixa' WHERE short_name = 'CTB'")
    ctx.commit()

    cycle_service.rebuild_blocks(cycle["id"], _plan(ctx)["plan"])
    depois = [b["short_name"] for b in cycle_service.blocks(cycle["id"])]
    # Fisica virou maxima: entra na primeira rodada, atras apenas de Portugues
    # (mesma prioridade, incidencia maior). CTB caiu para o fim.
    assert depois[0] == "Portugues"
    assert depois[1] == "Fisica"
    assert depois.index("Fisica") < depois.index("CTB")
    # Regerar volta a posicao para 1 (comportamento ja documentado).
    assert cycle_service.active_cycle()["current_position"] == 1


# --------------------------------------------------------------------------
# Invariantes da distribuicao
# --------------------------------------------------------------------------
def test_split_minutes_nunca_perde_nem_inventa_minuto():
    for total in (20, 45, 60, 90, 105, 120, 270, 420, 450, 1013):
        for parts in range(1, 7):
            blocks = cycle_service.split_minutes(total, parts)
            assert len(blocks) == parts
            assert sum(blocks) == total


def test_sequencia_nao_repete_disciplina_vizinha(ctx):
    sequence = _plan(ctx)["sequence"]
    repetidos = [i for i in range(1, len(sequence))
                 if sequence[i]["discipline_id"] == sequence[i - 1]["discipline_id"]]
    assert repetidos == []


def test_todas_as_disciplinas_continuam_cadastradas(ctx):
    """Corrigir a prioridade nao pode remover disciplina do edital."""
    assert scalar("SELECT COUNT(*) FROM disciplines", (), 0) == 14
    assert scalar("SELECT COUNT(*) FROM disciplines WHERE active = 1", (), 0) == 14
    incluidas = [i["short_name"] for i in _plan(ctx)["items"] if i["included"]]
    assert len(incluidas) == 14
