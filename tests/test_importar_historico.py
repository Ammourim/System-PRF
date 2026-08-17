"""Importacao do historico anterior ao sistema.

O risco desse script e duplo: apagar o que ja existe, ou duplicar ao rodar de
novo. Os dois casos estao cobertos aqui.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_db, insert, query_all, query_one, scalar  # noqa: E402
from scripts.importar_historico import (BLOCOS_ESTUDADOS, BLOCOS_ZERADOS,  # noqa: E402
                                        MINUTOS_POR_BLOCO, importar)


def _importar(app):
    with app.app_context():
        return importar(get_db())


def test_cria_assuntos_estudados_e_zerados(app):
    resumo = _importar(app)
    assert resumo["assuntos"] == len(BLOCOS_ESTUDADOS) == 10
    assert resumo["zerados"] == len(BLOCOS_ZERADOS) == 4
    assert resumo["ignorados"] == 0

    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM subjects", (), 0) == 14


def test_zerados_voltam_para_a_fila_de_teoria(app):
    """Bloco zerado nao pode ter revisao: perdeu as dele no sistema anterior."""
    _importar(app)
    with app.app_context():
        zerado = query_one(
            "SELECT * FROM subjects WHERE name LIKE 'Conceitos introdutorios%'")
        assert zerado["status"] == "nao_iniciada"
        assert "abaixo de 60%" in zerado["notes"]
        assert scalar("SELECT COUNT(*) FROM reviews WHERE subject_id = ?",
                      (zerado["id"],), 0) == 0


def test_revisoes_mantem_as_datas_do_extrato(app):
    _importar(app)
    with app.app_context():
        # Datas explicitas no extrato sao preservadas exatamente.
        esperado = {
            "CTB Art. 1o ao 19": ("2026-08-31", 2),
            "CTB Art. 20 ao 25-A": ("2026-09-01", 2),
            "CTB Art. 26 ao 29": ("2026-09-02", 2),
            "Morfologia": ("2026-08-18", 1),
            "Direito Administrativo - introducao": ("2026-08-16", 1),
            "Decreto 11.348/23": ("2026-08-20", 1),
        }
        for prefixo, (data, feitas) in esperado.items():
            row = query_one(
                "SELECT r.* FROM reviews r JOIN subjects s ON s.id = r.subject_id"
                " WHERE s.name LIKE ?", (f"{prefixo}%",))
            assert row is not None, prefixo
            assert row["next_date"] == data, prefixo
            assert row["times_done"] == feitas, prefixo
            assert row["step"] == feitas, prefixo


def test_revisoes_sem_data_usam_o_intervalo_do_sistema(app):
    """Os 4 R2 concluidos em 13-14/08 ganham R3 pelo intervalo padrao (+15)."""
    _importar(app)
    with app.app_context():
        row = query_one(
            "SELECT r.* FROM reviews r JOIN subjects s ON s.id = r.subject_id"
            " WHERE s.name LIKE 'Ortografia%'")
        assert row["last_done_at"] == "2026-08-13"
        assert row["next_date"] == "2026-08-28"   # 13/08 + 15 dias
        assert row["interval_days"] == 15


def test_sessoes_de_teoria_com_duracao_estimada(app):
    _importar(app)
    with app.app_context():
        sessoes = query_all("SELECT * FROM study_sessions WHERE type = 'teoria'")
        assert len(sessoes) == 10
        assert all(s["actual_minutes"] == MINUTOS_POR_BLOCO for s in sessoes)
        assert all("estimado" in s["notes"] for s in sessoes)
        # A data da sessao e a data real da teoria, nao a de hoje.
        datas = {s["date"] for s in sessoes}
        assert "2026-08-01" in datas and "2026-08-11" in datas


def test_rodar_duas_vezes_nao_duplica(app):
    primeiro = _importar(app)
    segundo = _importar(app)

    assert primeiro["assuntos"] == 10 and primeiro["revisoes"] == 10
    assert segundo == {"assuntos": 0, "sessoes": 0, "revisoes": 0, "zerados": 0,
                       "ignorados": 0}

    with app.app_context():
        assert scalar("SELECT COUNT(*) FROM subjects", (), 0) == 14
        assert scalar("SELECT COUNT(*) FROM study_sessions", (), 0) == 10
        assert scalar("SELECT COUNT(*) FROM reviews", (), 0) == 10


def test_nao_apaga_registros_existentes(app):
    """Requisito explicito: o que ja existe no sistema tem que sobreviver."""
    with app.app_context():
        subject_id = insert(
            "INSERT INTO subjects (discipline_id, name) VALUES (1, 'Assunto meu')")
        session_id = insert(
            "INSERT INTO study_sessions (date, discipline_id, subject_id, type,"
            " actual_minutes) VALUES ('2026-08-10', 1, ?, 'questoes', 45)", (subject_id,))
        review_id = insert(
            "INSERT INTO reviews (discipline_id, subject_id, origin_date, next_date)"
            " VALUES (1, ?, '2026-08-10', '2026-08-20')", (subject_id,))

    _importar(app)

    with app.app_context():
        assert query_one("SELECT * FROM subjects WHERE id = ?", (subject_id,)) is not None
        sessao = query_one("SELECT * FROM study_sessions WHERE id = ?", (session_id,))
        assert sessao["actual_minutes"] == 45
        revisao = query_one("SELECT * FROM reviews WHERE id = ?", (review_id,))
        assert revisao["next_date"] == "2026-08-20"
        # E os importados entraram por cima, sem conflito.
        assert scalar("SELECT COUNT(*) FROM subjects", (), 0) == 15


def test_assunto_preexistente_e_reaproveitado(app):
    """Se o assunto ja existe, o script usa o existente em vez de criar outro."""
    nome = BLOCOS_ESTUDADOS[0][3] + " (aulas 001-004)"
    with app.app_context():
        existente = insert(
            "INSERT INTO subjects (discipline_id, name, status) VALUES (1, ?, 'revisao')",
            (nome,))

    _importar(app)

    with app.app_context():
        iguais = query_all("SELECT * FROM subjects WHERE name = ?", (nome,))
        assert len(iguais) == 1
        assert iguais[0]["id"] == existente
        assert iguais[0]["status"] == "revisao"  # nao sobrescreve o status atual
