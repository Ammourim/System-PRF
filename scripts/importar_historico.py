"""Importa o historico de estudo anterior ao sistema (extrato de 13/08/2026).

Caracteristicas deliberadas:
  * ADITIVO: nunca apaga nem sobrescreve registro existente;
  * IDEMPOTENTE: rodar duas vezes nao duplica nada. Cada assunto e identificado
    pelo par (disciplina, nome); revisoes e sessoes so entram se ainda nao houver
    equivalente para aquele assunto.

Uso:
    python scripts/importar_historico.py            # aplica
    python scripts/importar_historico.py --dry-run  # so mostra o que faria
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402
from app.services import reviews as reviews_service  # noqa: E402
from app.utils import add_days, days_between  # noqa: E402

# Duracao estimada de cada bloco de teoria (escolha do usuario: 60 min fixos).
# E estimativa, nao medicao - fica registrado na observacao da sessao.
MINUTOS_POR_BLOCO = 60
OBS_TEORIA = "Importado do sistema anterior (tempo estimado em 60 min)."

# (bloco, sigla, aulas, assunto, data_teoria, [datas das revisoes feitas], proxima)
# proxima = None quando deve ser calculada pelos intervalos do sistema.
BLOCOS_ESTUDADOS = [
    (1, "CTB", "001-004", "CTB Art. 1o ao 19 - disposicoes preliminares e SNT",
     "2026-08-01", ["2026-08-07", "2026-08-10"], "2026-08-31"),
    (2, "Portugues", "001-005", "Ortografia, acentuacao e hifen",
     "2026-08-04", ["2026-08-07", "2026-08-13"], None),
    (3, "CTB", "005-007", "CTB Art. 20 ao 25-A - competencias do SNT",
     "2026-08-02", ["2026-08-07", "2026-08-11"], "2026-09-01"),
    (4, "Portugues", "006-010", "Morfologia",
     "2026-08-09", ["2026-08-11"], "2026-08-18"),
    (5, "Administrativo", "001-007", "Direito Administrativo - introducao",
     "2026-08-07", ["2026-08-09"], "2026-08-16"),
    (6, "Constitucional", "001-002", "Teoria da Constituicao e poder constituinte",
     "2026-08-05", ["2026-08-07", "2026-08-14"], None),
    (8, "Leg. Especial", "001-003", "Decreto 11.348/23 - estrutura e competencias da PRF",
     "2026-08-11", ["2026-08-13"], "2026-08-20"),
    (9, "CTB", "008-010", "CTB Art. 26 ao 29 - regras de circulacao",
     "2026-08-03", ["2026-08-07", "2026-08-12"], "2026-09-02"),
    (11, "CTB", "011-012", "CTB Art. 30 ao 39 - regras de circulacao II",
     "2026-08-04", ["2026-08-07", "2026-08-13"], None),
    (22, "CTB", "013-015", "CTB Art. 40 ao 50 - luzes, buzina, imobilizacao",
     "2026-08-05", ["2026-08-07", "2026-08-14"], None),
]

# Blocos zerados (acerto < 60%): voltaram para a fila de teoria e perderam as
# revisoes. Entram como assunto 'nao_iniciada', sem revisao agendada.
BLOCOS_ZERADOS = [
    (7, "Penal", "001-002",
     "Conceitos introdutorios - infracao penal e sujeitos do crime", "2026-08-09"),
    (14, "Constitucional", "001-002", "Bloco T2 - aulas 001-002", "2026-08-08"),
    (21, "Fisica", "001-004", "Aulas 001-004", "2026-08-11"),
    (24, "CTB", "016-018", "Aulas 016-018", "2026-08-08"),
]

OBS_ZERADO = ("Zerado em {data} no sistema anterior (acerto abaixo de 60%): "
              "voltou para a fila de teoria.")


def _disciplinas(db) -> dict[str, int]:
    return {r["short_name"]: r["id"]
            for r in db.execute("SELECT id, short_name FROM disciplines")}


def _assunto_id(db, discipline_id: int, nome: str) -> int | None:
    row = db.execute(
        "SELECT id FROM subjects WHERE discipline_id = ? AND lower(name) = lower(?)",
        (discipline_id, nome)).fetchone()
    return row["id"] if row else None


def importar(db, dry_run: bool = False) -> dict:
    disciplinas = _disciplinas(db)
    resumo = {"assuntos": 0, "sessoes": 0, "revisoes": 0, "zerados": 0, "ignorados": 0}
    intervalos = reviews_service.intervals()

    def proximo_intervalo(passo: int) -> int:
        return intervalos[passo] if passo < len(intervalos) else intervalos[-1]

    # ---------------------------------------------------------- estudados
    for bloco, sigla, aulas, assunto, teoria, feitas, proxima in BLOCOS_ESTUDADOS:
        discipline_id = disciplinas.get(sigla)
        if not discipline_id:
            print(f"  ! disciplina '{sigla}' nao encontrada - bloco #{bloco} ignorado")
            resumo["ignorados"] += 1
            continue

        nome = f"{assunto} (aulas {aulas})"
        subject_id = _assunto_id(db, discipline_id, nome)
        if subject_id is None:
            if dry_run:
                # Id inexistente: as checagens seguintes nao encontram nada e a
                # simulacao conta sessao e revisao como o real faria.
                subject_id = -bloco
            else:
                cur = db.execute(
                    "INSERT INTO subjects (discipline_id, name, status, notes)"
                    " VALUES (?, ?, 'em_andamento', ?)",
                    (discipline_id, nome,
                     f"Importado do sistema anterior. Teoria em {teoria}."))
                subject_id = cur.lastrowid
            resumo["assuntos"] += 1
            print(f"  + assunto  #{bloco:2d} {sigla:14s} {nome}")
        else:
            print(f"  = assunto  #{bloco:2d} ja existe, mantido: {nome}")

        # Sessao de teoria (uma so por assunto/data).
        ja_tem = db.execute(
            "SELECT 1 FROM study_sessions WHERE subject_id = ? AND date = ? AND type = 'teoria'",
            (subject_id, teoria)).fetchone() if subject_id else None
        if subject_id and not ja_tem:
            if not dry_run:
                db.execute(
                    "INSERT INTO study_sessions (date, discipline_id, subject_id, type,"
                    " planned_minutes, actual_minutes, notes, completed)"
                    " VALUES (?, ?, ?, 'teoria', ?, ?, ?, 1)",
                    (teoria, discipline_id, subject_id, MINUTOS_POR_BLOCO,
                     MINUTOS_POR_BLOCO, OBS_TEORIA))
            resumo["sessoes"] += 1

        # Revisao: uma por assunto, ja no passo correto.
        tem_revisao = db.execute(
            "SELECT 1 FROM reviews WHERE subject_id = ?", (subject_id,)).fetchone() \
            if subject_id else None
        if subject_id and not tem_revisao:
            passo = len(feitas)              # quantas revisoes ja foram feitas
            ultima = feitas[-1] if feitas else teoria
            if proxima:
                # Data ja definida no extrato: manter exatamente.
                proxima_data = proxima
                intervalo = max(1, days_between(ultima, proxima_data))
            else:
                # Sem data no extrato: calcular pelos intervalos do sistema.
                intervalo = proximo_intervalo(passo)
                proxima_data = add_days(ultima, intervalo)

            if not dry_run:
                db.execute(
                    "INSERT INTO reviews (discipline_id, subject_id, title, origin_date,"
                    " next_date, step, interval_days, difficulty, method, status,"
                    " last_done_at, times_done, notes)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'media', 'questoes', 'pendente', ?, ?, ?)",
                    (discipline_id, subject_id, assunto[:120], teoria, proxima_data,
                     passo, intervalo, ultima if feitas else None, passo,
                     f"Importado: R1..R{passo} feitas em {', '.join(feitas)}."
                     if feitas else "Importado do sistema anterior."))
            resumo["revisoes"] += 1
            print(f"      revisao: {passo} feita(s), proxima em {proxima_data}")

    # ------------------------------------------------------------ zerados
    for bloco, sigla, aulas, assunto, zerado_em in BLOCOS_ZERADOS:
        discipline_id = disciplinas.get(sigla)
        if not discipline_id:
            resumo["ignorados"] += 1
            continue
        nome = f"{assunto} (aulas {aulas})"
        if _assunto_id(db, discipline_id, nome) is None:
            if not dry_run:
                db.execute(
                    "INSERT INTO subjects (discipline_id, name, status, notes)"
                    " VALUES (?, ?, 'nao_iniciada', ?)",
                    (discipline_id, nome, OBS_ZERADO.format(data=zerado_em)))
            resumo["zerados"] += 1
            print(f"  + zerado   #{bloco:2d} {sigla:14s} {nome}")
        else:
            print(f"  = zerado   #{bloco:2d} ja existe, mantido: {nome}")

    if not dry_run:
        db.commit()
    return resumo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="mostra o que seria feito, sem gravar")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db = get_db()
        antes = {
            "assuntos": db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
            "sessoes": db.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0],
            "revisoes": db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
        }
        print(f"\nAntes: {antes['assuntos']} assuntos, {antes['sessoes']} sessoes, "
              f"{antes['revisoes']} revisoes")
        print("\nImportando historico do sistema anterior"
              f"{' (SIMULACAO)' if args.dry_run else ''}:\n")

        resumo = importar(db, dry_run=args.dry_run)

        depois = {
            "assuntos": db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
            "sessoes": db.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0],
            "revisoes": db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
        }
        print(f"\nCriados: {resumo['assuntos']} assuntos estudados, "
              f"{resumo['zerados']} zerados, {resumo['sessoes']} sessoes, "
              f"{resumo['revisoes']} revisoes")
        print(f"Depois: {depois['assuntos']} assuntos, {depois['sessoes']} sessoes, "
              f"{depois['revisoes']} revisoes")
        if resumo["ignorados"]:
            print(f"ATENCAO: {resumo['ignorados']} bloco(s) ignorado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
