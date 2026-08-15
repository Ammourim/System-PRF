"""Dados iniciais (disciplinas, configuracoes, primeiro ciclo) e dados de demo.

`ensure_base_data` e idempotente e roda em todo start: garante que o sistema
abra utilizavel. `seed_demo` insere registros marcados com is_demo = 1, que
aparecem sinalizados na interface e podem ser removidos em Configuracoes.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from .services.cycle import plan_from_disciplines, spread
from .services.settings import DEFAULTS
from .utils import percentage, to_iso, today as today_date

# (nome, sigla, incidencia %, prioridade, status, bloco min, meta min/ciclo)
DISCIPLINES: list[tuple] = [
    ("Legislacao de Transito", "CTB", 25.00, "maxima", "em_andamento", 90, 420),
    ("Lingua Portuguesa", "Portugues", 15.00, "maxima", "em_andamento", 90, 270),
    ("Lingua Estrangeira - Espanhol", "Espanhol", 6.70, "base", "nao_iniciada", 60, 90),
    ("Direito Administrativo", "Administrativo", 5.80, "base", "em_andamento", 90, 120),
    ("Direito Constitucional", "Constitucional", 5.80, "base", "em_andamento", 90, 120),
    ("Informatica", "Informatica", 5.80, "base", "nao_iniciada", 60, 120),
    ("Raciocinio Logico-Matematico", "RLM", 5.00, "base", "em_andamento", 60, 120),
    ("Legislacao Especial", "Leg. Especial", 5.00, "base", "em_andamento", 60, 105),
    ("Etica e Cidadania", "Etica", 5.00, "base", "em_andamento", 60, 90),
    ("Direito Penal", "Penal", 4.20, "complementar", "em_andamento", 60, 90),
    ("Direito Processual Penal", "Processo Penal", 4.20, "complementar", "em_andamento", 60, 90),
    ("Direitos Humanos", "Dir. Humanos", 4.20, "complementar", "nao_iniciada", 45, 60),
    ("Geopolitica", "Geopolitica", 4.20, "complementar", "nao_iniciada", 45, 60),
    ("Fisica", "Fisica", 4.00, "complementar", "nao_iniciada", 45, 60),
]

TAF_TESTS = [
    ("Corrida 12 minutos", "metros", 1, None, 2800.0),
    ("Barra fixa", "repeticoes", 1, None, 10.0),
    ("Flexao de bracos", "repeticoes", 1, None, 30.0),
    ("Abdominal (1 min)", "repeticoes", 1, None, 40.0),
]

DEMO_SUBJECTS: dict[str, list[str]] = {
    "CTB": ["Infracoes", "Penalidades e medidas administrativas", "Sinalizacao",
            "Habilitacao", "Normas gerais de circulacao"],
    "Portugues": ["Interpretacao de texto", "Crase", "Concordancia verbal", "Hifen",
                  "Pontuacao"],
    "Constitucional": ["Direitos fundamentais", "Organizacao do Estado",
                       "Seguranca publica"],
    "Administrativo": ["Atos administrativos", "Poderes administrativos",
                       "Licitacoes"],
    "RLM": ["Proposicoes logicas", "Tabelas verdade", "Analise combinatoria"],
    "Penal": ["Aplicacao da lei penal", "Crimes contra a administracao publica"],
    "Processo Penal": ["Prisao em flagrante", "Inquerito policial"],
    "Leg. Especial": ["Lei de drogas", "Estatuto do desarmamento"],
    "Etica": ["Codigo de etica do servidor publico"],
}


# --------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------
def ensure_base_data(conn: sqlite3.Connection) -> None:
    _ensure_settings(conn)
    _ensure_disciplines(conn)
    _ensure_taf_tests(conn)
    _ensure_first_cycle(conn)
    conn.commit()


def _ensure_settings(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )


def _ensure_disciplines(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM disciplines").fetchone()[0]
    if existing:
        return
    for position, item in enumerate(DISCIPLINES, start=1):
        name, short, incidence, priority, status, block, target = item
        conn.execute(
            "INSERT INTO disciplines (name, short_name, incidence, priority, status,"
            " block_minutes, target_minutes, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, short, incidence, priority, status, block, target, position),
        )


def _ensure_taf_tests(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM taf_tests").fetchone()[0]:
        return
    for name, unit, higher, current, goal in TAF_TESTS:
        conn.execute(
            "INSERT INTO taf_tests (name, unit, higher_is_better, current_mark, goal_mark,"
            " notes) VALUES (?, ?, ?, ?, ?, ?)",
            (name, unit, higher, current, goal,
             "Meta de referencia - ajustar quando o edital sair."),
        )


def _ensure_first_cycle(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM study_cycles").fetchone()[0]:
        return
    rows = conn.execute(
        "SELECT id, name, block_minutes, target_minutes FROM disciplines"
        " WHERE active = 1 ORDER BY incidence DESC, position"
    ).fetchall()
    plan = plan_from_disciplines(rows)
    start = today_date()
    days = int(DEFAULTS["cycle_days"])
    cur = conn.execute(
        "INSERT INTO study_cycles (number, name, start_date, end_date, days, goal_minutes,"
        " goal_questions, current_position, status) VALUES (1, 'Ciclo #01', ?, ?, ?, ?, ?, 1,"
        " 'ativo')",
        (to_iso(start), to_iso(start + timedelta(days=days - 1)), days,
         int(DEFAULTS["prf_goal_minutes"]), int(DEFAULTS["questions_goal_per_cycle"])),
    )
    cycle_id = cur.lastrowid
    _insert_blocks(conn, cycle_id, plan)


def _insert_blocks(conn: sqlite3.Connection, cycle_id: int, plan: list[dict]) -> None:
    sizes = {int(DEFAULTS["block_long"]): "longo",
             int(DEFAULTS["block_medium"]): "medio",
             int(DEFAULTS["block_short"]): "curto"}
    for position, item in enumerate(spread(plan), start=1):
        minutes = int(item["block_minutes"])
        conn.execute(
            "INSERT INTO cycle_blocks (cycle_id, position, discipline_id, planned_minutes,"
            " block_size) VALUES (?, ?, ?, ?, ?)",
            (cycle_id, position, item["discipline_id"], minutes, sizes.get(minutes, "custom")),
        )


# --------------------------------------------------------------------------
# Demonstracao
# --------------------------------------------------------------------------
def has_demo(conn: sqlite3.Connection) -> bool:
    tables = ["subjects", "study_sessions", "questions", "mistakes", "reviews",
              "mock_exams", "taf_workouts", "taf_measurements", "college_subjects",
              "college_tasks", "college_sessions"]
    for table in tables:
        if conn.execute(f"SELECT COUNT(*) FROM {table} WHERE is_demo = 1").fetchone()[0]:
            return True
    return False


def clear_demo(conn: sqlite3.Connection) -> None:
    """Remove tudo que foi marcado como demonstracao, na ordem das dependencias."""
    for table in ["mock_exam_results"]:
        conn.execute(
            f"DELETE FROM {table} WHERE mock_exam_id IN"
            " (SELECT id FROM mock_exams WHERE is_demo = 1)")
    for table in ["questions", "mistakes", "reviews", "study_sessions", "mock_exams",
                  "taf_measurements", "taf_workouts", "college_tasks", "college_sessions",
                  "college_subjects", "subjects"]:
        conn.execute(f"DELETE FROM {table} WHERE is_demo = 1")
    conn.execute("UPDATE cycle_blocks SET subject_id = NULL WHERE subject_id NOT IN"
                 " (SELECT id FROM subjects)")
    conn.commit()


def seed_demo(conn: sqlite3.Connection) -> None:
    """Insere um conjunto pequeno e coerente de dados de demonstracao."""
    if has_demo(conn):
        return

    disciplines = {r["short_name"]: r["id"]
                   for r in conn.execute("SELECT id, short_name FROM disciplines")}
    subjects: dict[tuple[str, str], int] = {}
    for short, names in DEMO_SUBJECTS.items():
        did = disciplines.get(short)
        if not did:
            continue
        for name in names:
            existing = conn.execute(
                "SELECT id FROM subjects WHERE discipline_id = ? AND name = ?",
                (did, name)).fetchone()
            if existing:
                subjects[(short, name)] = existing["id"]
                continue
            cur = conn.execute(
                "INSERT INTO subjects (discipline_id, name, status, is_demo)"
                " VALUES (?, ?, 'em_andamento', 1)",
                (did, name),
            )
            subjects[(short, name)] = cur.lastrowid

    today = today_date()

    def day(offset: int) -> str:
        return to_iso(today - timedelta(days=offset))

    cycle = conn.execute(
        "SELECT id FROM study_cycles WHERE status = 'ativo' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    cycle_id = cycle["id"] if cycle else None

    # (dias atras, sigla, assunto, tipo, planejado, realizado, questoes, acertos, obs)
    sessions = [
        (11, "CTB", "Infracoes", "teoria", 90, 85, 0, 0, "Leitura do capitulo + esquema."),
        (11, "CTB", "Infracoes", "questoes", 45, 50, 30, 16,
         "Confundi penalidade com medida administrativa."),
        (10, "Portugues", "Crase", "teoria", 90, 60, 0, 0, "Plantao curto."),
        (9, "Constitucional", "Direitos fundamentais", "questoes", 60, 60, 25, 16, ""),
        (8, "RLM", "Proposicoes logicas", "teoria", 60, 60, 0, 0, "Base fraca, refazer."),
        (8, "RLM", "Proposicoes logicas", "questoes", 45, 40, 20, 9, "Tabela verdade travou."),
        (7, "CTB", "Sinalizacao", "teoria", 90, 90, 0, 0, ""),
        (6, "Portugues", "Interpretacao de texto", "questoes", 60, 65, 30, 24, ""),
        (5, "Administrativo", "Atos administrativos", "teoria", 90, 75, 0, 0, ""),
        (4, "Penal", "Aplicacao da lei penal", "questoes", 60, 60, 20, 14, ""),
        (3, "CTB", "Penalidades e medidas administrativas", "revisao", 45, 45, 25, 18,
         "Revisao por questoes."),
        (2, "Portugues", "Concordancia verbal", "questoes", 60, 55, 30, 21, ""),
        (1, "Leg. Especial", "Lei de drogas", "teoria", 60, 60, 0, 0, ""),
        (1, "CTB", "Infracoes", "questoes", 45, 45, 25, 17, "Melhorou em relacao ao inicio."),
    ]
    for offset, short, subject, kind, planned, actual, total, correct, note in sessions:
        did = disciplines.get(short)
        sid = subjects.get((short, subject))
        cur = conn.execute(
            "INSERT INTO study_sessions (date, discipline_id, subject_id, type, planned_minutes,"
            " actual_minutes, notes, completed, cycle_id, is_demo)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 1)",
            (day(offset), did, sid, kind, planned, actual, note, cycle_id),
        )
        session_id = cur.lastrowid
        if total:
            conn.execute(
                "INSERT INTO questions (date, discipline_id, subject_id, total, correct, wrong,"
                " percentage, banca, source, kind, notes, session_id, is_demo)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'Cebraspe', 'Caderno de questoes', ?, ?, ?, 1)",
                (day(offset), did, sid, total, correct, total - correct,
                 percentage(correct, total), "revisao" if kind == "revisao" else "novo",
                 note, session_id),
            )

    mistakes = [
        (10, "CTB", "Infracoes", "Multa x medida administrativa em infracao de transito",
         "C", "Medida administrativa nao e penalidade.", "aberto"),
        (8, "RLM", "Proposicoes logicas", "Negacao de proposicao composta", "C",
         "Aplicar De Morgan.", "aberto"),
        (8, "RLM", "Tabelas verdade", "Condicional com 3 proposicoes", "A",
         "Errei a montagem das linhas.", "aberto"),
        (6, "Portugues", "Interpretacao de texto", "Inferencia do paragrafo 3", "I",
         "Li rapido demais.", "revisado"),
        (4, "Penal", "Aplicacao da lei penal", "Lei penal no tempo", "E",
         "Sabia, mas esqueci a excecao.", "aberto"),
        (2, "Portugues", "Concordancia verbal", "Sujeito composto posposto", "D",
         "Fiquei entre duas alternativas.", "aberto"),
    ]
    for offset, short, subject, ref, category, explanation, status in mistakes:
        conn.execute(
            "INSERT INTO mistakes (date, discipline_id, subject_id, question_ref, category,"
            " explanation, status, is_demo) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (day(offset), disciplines.get(short), subjects.get((short, subject)), ref,
             category, explanation, status),
        )

    # (dias desde a origem, sigla, assunto, passo, intervalo, dias ate a proxima)
    reviews = [
        (11, "CTB", "Infracoes", 1, 7, -1, "questoes"),
        (10, "Portugues", "Crase", 1, 7, 0, "recuperacao_ativa"),
        (9, "Constitucional", "Direitos fundamentais", 0, 1, 0, "questoes"),
        (8, "RLM", "Proposicoes logicas", 0, 1, -2, "caderno_erros"),
        (7, "CTB", "Sinalizacao", 0, 1, 2, "flashcards"),
        (4, "Penal", "Aplicacao da lei penal", 0, 1, 3, "questoes"),
    ]
    for offset, short, subject, step, interval, next_offset, method in reviews:
        conn.execute(
            "INSERT INTO reviews (discipline_id, subject_id, title, origin_date, next_date,"
            " step, interval_days, difficulty, method, status, times_done, is_demo)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'media', ?, 'pendente', ?, 1)",
            (disciplines.get(short), subjects.get((short, subject)), subject, day(offset),
             to_iso(today + timedelta(days=next_offset)), step, interval, method, step),
        )

    cur = conn.execute(
        "INSERT INTO mock_exams (name, date, banca, prova, total, correct, wrong, percentage,"
        " total_minutes, planned_minutes, time_left_minutes, slow_questions, guessed_questions,"
        " skipped_questions, perception, notes, is_demo)"
        " VALUES ('Simulado #01', ?, 'Cebraspe', 'PRF 2021 - prova adaptada', 120, 76, 44, 63.33,"
        " 285, 300, 15, '14, 37, 58', '22, 71, 90, 104', '37, 58',"
        " 'Perdi tempo em RLM no comeco e corri no final.',"
        " 'Primeiro simulado completo do ciclo.', 1)",
        (day(6),),
    )
    mock_id = cur.lastrowid
    mock_results = [
        ("CTB", 30, 21), ("Portugues", 18, 14), ("Constitucional", 12, 8),
        ("Administrativo", 12, 7), ("RLM", 10, 5), ("Penal", 8, 5),
        ("Processo Penal", 8, 5), ("Leg. Especial", 8, 5), ("Etica", 6, 4),
        ("Informatica", 8, 2),
    ]
    for short, total, correct in mock_results:
        did = disciplines.get(short)
        if not did:
            continue
        conn.execute(
            "INSERT INTO mock_exam_results (mock_exam_id, discipline_id, total, correct, wrong,"
            " percentage) VALUES (?, ?, ?, ?, ?, ?)",
            (mock_id, did, total, correct, total - correct, percentage(correct, total)),
        )

    taf_values = {
        "Corrida 12 minutos": [(28, 2350.0), (14, 2480.0), (2, 2560.0)],
        "Barra fixa": [(28, 4.0), (14, 5.0), (2, 6.0)],
        "Flexao de bracos": [(28, 18.0), (2, 23.0)],
        "Abdominal (1 min)": [(28, 28.0), (2, 33.0)],
    }
    for name, values in taf_values.items():
        row = conn.execute("SELECT id FROM taf_tests WHERE name = ?", (name,)).fetchone()
        if not row:
            continue
        for offset, value in values:
            conn.execute(
                "INSERT INTO taf_measurements (test_id, date, value, is_demo)"
                " VALUES (?, ?, ?, 1)", (row["id"], day(offset), value))
        last_offset, last_value = values[-1]
        conn.execute(
            "UPDATE taf_tests SET current_mark = ?, measured_at = ? WHERE id = ?",
            (last_value, day(last_offset), row["id"]))

    workouts = [
        (9, "Treino A - Corrida", "corrida", 50, "Aquecimento + intervalado 6x400m",
         None, None, 6.0, "concluido"),
        (7, "Treino B - Forca", "forca", 45, "Barra + flexao + abdominal", 4, 8, None,
         "concluido"),
        (5, "Treino A - Corrida", "corrida", 55, "Continuo 8km leve", None, None, 8.0,
         "concluido"),
        (3, "Treino B - Forca", "forca", 45, "Barra negativa + flexao", 4, 10, None,
         "pendente"),
        (-1, "Treino A - Corrida", "corrida", 50, "Intervalado 8x400m", None, None, 6.5,
         "planejado"),
        (-3, "Treino B - Forca", "forca", 45, "Circuito TAF", 4, 10, None, "planejado"),
    ]
    for offset, name, kind, duration, exercise, sets, reps, distance, status in workouts:
        conn.execute(
            "INSERT INTO taf_workouts (date, name, type, duration_minutes, exercise, sets, reps,"
            " distance_km, status, is_demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (day(offset), name, kind, duration, exercise, sets, reps, distance, status))

    college = [("Metodologia Cientifica", "Prof. Silva"), ("Estatistica Aplicada", "Prof. Souza")]
    college_ids = []
    for name, professor in college:
        cur = conn.execute(
            "INSERT INTO college_subjects (name, professor, is_demo) VALUES (?, ?, 1)",
            (name, professor))
        college_ids.append(cur.lastrowid)
    conn.execute(
        "INSERT INTO college_tasks (college_subject_id, title, type, due_date, status, is_demo)"
        " VALUES (?, 'Entrega do artigo - parte 1', 'trabalho', ?, 'aberta', 1)",
        (college_ids[0], to_iso(today + timedelta(days=5))))
    conn.execute(
        "INSERT INTO college_tasks (college_subject_id, title, type, due_date, status, is_demo)"
        " VALUES (?, 'Prova 1', 'prova', ?, 'aberta', 1)",
        (college_ids[1], to_iso(today + timedelta(days=12))))
    for offset, subject_idx, minutes in [(6, 0, 90), (3, 1, 60), (1, 0, 60)]:
        conn.execute(
            "INSERT INTO college_sessions (date, college_subject_id, minutes, is_demo)"
            " VALUES (?, ?, ?, 1)", (day(offset), college_ids[subject_idx], minutes))

    conn.commit()
