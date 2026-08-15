"""Testes do ciclo: geracao dos blocos, avanco da posicao e progresso."""

from app.db import query_all, query_one, scalar
from app.services import cycle as cycle_service
from app.utils import today_iso


def test_spread_intercala_disciplinas():
    plan = [
        {"discipline_id": 1, "name": "CTB", "count": 4, "block_minutes": 90},
        {"discipline_id": 2, "name": "Portugues", "count": 2, "block_minutes": 90},
        {"discipline_id": 3, "name": "RLM", "count": 1, "block_minutes": 60},
    ]
    ordered = [item["name"] for item in cycle_service.spread(plan)]
    assert len(ordered) == 7
    # Nenhuma disciplina deve aparecer duas vezes seguidas quando ha alternativa.
    assert not any(ordered[i] == ordered[i + 1] for i in range(len(ordered) - 1))


def test_spread_nao_repete_disciplina_em_sequencia_no_plano_real(ctx):
    """O ciclo V1 (14 disciplinas, 27 blocos) nao pode ter dois blocos iguais seguidos."""
    rows = query_all("SELECT id, name, block_minutes, target_minutes FROM disciplines"
                     " WHERE active = 1")
    ordered = cycle_service.spread(cycle_service.plan_from_disciplines(rows))
    assert len(ordered) == 27
    repetidos = [i for i in range(1, len(ordered))
                 if ordered[i]["discipline_id"] == ordered[i - 1]["discipline_id"]]
    assert repetidos == []


def test_spread_tolera_disciplina_dominante():
    """Se uma disciplina tem quase todos os blocos, a funcao nao trava nem perde blocos."""
    plan = [
        {"discipline_id": 1, "name": "CTB", "count": 8, "block_minutes": 90},
        {"discipline_id": 2, "name": "Portugues", "count": 1, "block_minutes": 90},
    ]
    ordered = cycle_service.spread(plan)
    assert len(ordered) == 9
    assert sum(1 for i in ordered if i["discipline_id"] == 1) == 8


def test_spread_ignora_count_zero():
    plan = [{"discipline_id": 1, "name": "A", "count": 0, "block_minutes": 60}]
    assert cycle_service.spread(plan) == []


def test_plan_from_disciplines_arredonda_blocos():
    rows = [
        {"id": 1, "name": "CTB", "block_minutes": 90, "target_minutes": 420},
        {"id": 2, "name": "DH", "block_minutes": 45, "target_minutes": 60},
        {"id": 3, "name": "Fora", "block_minutes": 60, "target_minutes": 0},
    ]
    plan = cycle_service.plan_from_disciplines(rows)
    assert [p["count"] for p in plan] == [5, 1]  # 420/90 -> 5 ; 60/45 -> 1
    assert len(plan) == 2  # meta 0 fica fora do ciclo


def test_ciclo_inicial_criado_no_start(ctx):
    cycle = cycle_service.active_cycle()
    assert cycle is not None
    assert cycle["current_position"] == 1
    assert cycle_service.total_blocks(cycle["id"]) > 0


def test_avancar_marca_bloco_e_move_posicao(ctx):
    cycle = cycle_service.active_cycle()
    block = cycle_service.next_block(cycle)
    assert block["position"] == 1

    cycle_service.advance(cycle["id"], block["id"])

    cycle = cycle_service.active_cycle()
    assert cycle["current_position"] == 2
    assert query_one("SELECT done FROM cycle_blocks WHERE id = ?", (block["id"],))["done"] == 1
    assert cycle_service.next_block(cycle)["position"] == 2


def test_avancar_sem_marcar_nao_conclui_bloco(ctx):
    cycle = cycle_service.active_cycle()
    block = cycle_service.next_block(cycle)
    cycle_service.advance(cycle["id"], block["id"], mark_done=False)
    assert query_one("SELECT done FROM cycle_blocks WHERE id = ?", (block["id"],))["done"] == 0
    assert cycle_service.active_cycle()["current_position"] == 2


def test_posicao_nao_passa_do_fim(ctx):
    cycle = cycle_service.active_cycle()
    total = cycle_service.total_blocks(cycle["id"])
    cycle_service.set_position(cycle["id"], total + 50)
    assert cycle_service.active_cycle()["current_position"] == total + 1
    assert cycle_service.next_block() is None


def test_perder_dias_nao_altera_posicao(ctx):
    """Regra 42: ficar sem estudar nao muda o ciclo nem cria pendencia."""
    cycle = cycle_service.active_cycle()
    before = cycle["current_position"]
    # Nenhuma acao do usuario = nenhuma mudanca de estado.
    assert cycle_service.active_cycle()["current_position"] == before
    assert scalar("SELECT COUNT(*) FROM cycle_blocks WHERE done = 1", (), 0) == 0


def test_progresso_calcula_meta_e_realizado(ctx):
    cycle = cycle_service.active_cycle()
    ctx.execute(
        "INSERT INTO study_sessions (date, discipline_id, type, planned_minutes,"
        " actual_minutes, cycle_id) VALUES (?, 1, 'teoria', 90, 100, ?)",
        (today_iso(), cycle["id"]))
    ctx.execute(
        "INSERT INTO questions (date, discipline_id, total, correct, wrong, percentage)"
        " VALUES (?, 1, 20, 15, 5, 75.0)", (today_iso(),))
    ctx.commit()

    progress = cycle_service.progress()
    assert progress["minutes"] == 100
    assert progress["questions"] == 20
    assert progress["accuracy"] == 75.0
    assert progress["goal_minutes"] == 1800
    assert progress["minutes_pct"] == round(100 / 1800 * 100, 1)


def test_rebuild_blocks_reseta_posicao(ctx):
    cycle = cycle_service.active_cycle()
    cycle_service.set_position(cycle["id"], 5)
    plan = [{"discipline_id": 1, "block_minutes": 60, "count": 3}]
    total = cycle_service.rebuild_blocks(cycle["id"], plan)
    assert total == 3
    assert cycle_service.active_cycle()["current_position"] == 1
    assert len(query_all("SELECT id FROM cycle_blocks WHERE cycle_id = ?", (cycle["id"],))) == 3


def test_criar_novo_ciclo_encerra_o_anterior(ctx):
    old = cycle_service.active_cycle()
    plan = [{"discipline_id": 1, "block_minutes": 90, "count": 2}]
    new_id = cycle_service.create_cycle(plan)
    assert new_id != old["id"]
    assert query_one("SELECT status FROM study_cycles WHERE id = ?", (old["id"],))["status"] \
        == "encerrado"
    assert cycle_service.active_cycle()["id"] == new_id
