-- Migration 001 - estrutura inicial do Sistema PRF.
-- Convencoes:
--   * datas ISO (YYYY-MM-DD) em TEXT;
--   * duracoes sempre em MINUTOS (inteiro);
--   * is_demo = 1 marca registro de demonstracao (removivel em Configuracoes).

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE disciplines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    short_name          TEXT NOT NULL,
    incidence           REAL NOT NULL DEFAULT 0,      -- % historica de incidencia
    priority            TEXT NOT NULL DEFAULT 'base', -- maxima | base | complementar
    status              TEXT NOT NULL DEFAULT 'nao_iniciada',
                        -- nao_iniciada | em_andamento | revisao | consolidada
    block_minutes       INTEGER NOT NULL DEFAULT 60,  -- tamanho padrao do bloco
    target_minutes      INTEGER NOT NULL DEFAULT 0,   -- meta de minutos por ciclo
    position            INTEGER NOT NULL DEFAULT 0,   -- ordem de exibicao
    active              INTEGER NOT NULL DEFAULT 1,
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE subjects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id   INTEGER NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'nao_iniciada',
    notes           TEXT NOT NULL DEFAULT '',
    is_demo         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (discipline_id, name)
);
CREATE INDEX idx_subjects_discipline ON subjects(discipline_id);

CREATE TABLE study_cycles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    number              INTEGER NOT NULL,
    name                TEXT NOT NULL DEFAULT '',
    start_date          TEXT NOT NULL,
    end_date            TEXT,
    days                INTEGER NOT NULL DEFAULT 14,
    goal_minutes        INTEGER NOT NULL DEFAULT 1800,
    goal_questions      INTEGER NOT NULL DEFAULT 350,
    current_position    INTEGER NOT NULL DEFAULT 1,   -- posicao atual no ciclo
    status              TEXT NOT NULL DEFAULT 'ativo', -- ativo | encerrado
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_cycles_status ON study_cycles(status);

CREATE TABLE cycle_blocks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id            INTEGER NOT NULL REFERENCES study_cycles(id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
    subject_id          INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    planned_minutes     INTEGER NOT NULL DEFAULT 60,
    block_size          TEXT NOT NULL DEFAULT 'medio', -- longo | medio | curto | custom
    focus               TEXT NOT NULL DEFAULT '',      -- anotacao livre do bloco
    done                INTEGER NOT NULL DEFAULT 0,
    done_at             TEXT,
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_blocks_cycle ON cycle_blocks(cycle_id, position);

CREATE TABLE study_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    discipline_id       INTEGER REFERENCES disciplines(id) ON DELETE SET NULL,
    subject_id          INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    type                TEXT NOT NULL DEFAULT 'teoria',
                        -- teoria|questoes|revisao|simulado|correcao_simulado|redacao|outro
    planned_minutes     INTEGER NOT NULL DEFAULT 0,
    actual_minutes      INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT '',
    completed           INTEGER NOT NULL DEFAULT 1,
    cycle_id            INTEGER REFERENCES study_cycles(id) ON DELETE SET NULL,
    block_id            INTEGER REFERENCES cycle_blocks(id) ON DELETE SET NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_sessions_date ON study_sessions(date);
CREATE INDEX idx_sessions_discipline ON study_sessions(discipline_id);
CREATE INDEX idx_sessions_cycle ON study_sessions(cycle_id);

CREATE TABLE questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    discipline_id   INTEGER REFERENCES disciplines(id) ON DELETE SET NULL,
    subject_id      INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    total           INTEGER NOT NULL,
    correct         INTEGER NOT NULL,
    wrong           INTEGER NOT NULL,
    percentage      REAL NOT NULL,
    banca           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    kind            TEXT NOT NULL DEFAULT 'novo',  -- novo | revisao
    notes           TEXT NOT NULL DEFAULT '',
    session_id      INTEGER REFERENCES study_sessions(id) ON DELETE SET NULL,
    is_demo         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_questions_date ON questions(date);
CREATE INDEX idx_questions_discipline ON questions(discipline_id);
CREATE INDEX idx_questions_subject ON questions(subject_id);

CREATE TABLE mistakes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    discipline_id   INTEGER REFERENCES disciplines(id) ON DELETE SET NULL,
    subject_id      INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    question_ref    TEXT NOT NULL DEFAULT '',   -- enunciado curto / codigo da questao
    category        TEXT NOT NULL DEFAULT 'C',  -- C | E | I | A | D | CH
    explanation     TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    needs_review    INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'aberto', -- aberto | revisado | consolidado
    mock_exam_id    INTEGER REFERENCES mock_exams(id) ON DELETE SET NULL,
    is_demo         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_mistakes_status ON mistakes(status);
CREATE INDEX idx_mistakes_discipline ON mistakes(discipline_id);

CREATE TABLE reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id   INTEGER NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
    subject_id      INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    title           TEXT NOT NULL DEFAULT '',
    origin_date     TEXT NOT NULL,
    next_date       TEXT NOT NULL,
    step            INTEGER NOT NULL DEFAULT 0,   -- indice na lista de intervalos
    interval_days   INTEGER NOT NULL DEFAULT 1,
    difficulty      TEXT NOT NULL DEFAULT 'media', -- facil | media | dificil
    method          TEXT NOT NULL DEFAULT 'questoes',
                    -- questoes|flashcards|recuperacao_ativa|releitura|caderno_erros|mista
    status          TEXT NOT NULL DEFAULT 'pendente', -- pendente | concluida | arquivada
    last_done_at    TEXT,
    times_done      INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    is_demo         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_reviews_next ON reviews(status, next_date);
CREATE INDEX idx_reviews_discipline ON reviews(discipline_id);

CREATE TABLE mock_exams (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    date                TEXT NOT NULL,
    banca               TEXT NOT NULL DEFAULT '',
    prova               TEXT NOT NULL DEFAULT '',
    total               INTEGER NOT NULL DEFAULT 0,
    correct             INTEGER NOT NULL DEFAULT 0,
    wrong               INTEGER NOT NULL DEFAULT 0,
    percentage          REAL NOT NULL DEFAULT 0,
    total_minutes       INTEGER NOT NULL DEFAULT 0,
    planned_minutes     INTEGER NOT NULL DEFAULT 0,
    time_left_minutes   INTEGER NOT NULL DEFAULT 0,
    slow_questions      TEXT NOT NULL DEFAULT '',  -- questoes que consumiram muito tempo
    guessed_questions   TEXT NOT NULL DEFAULT '',  -- questoes chutadas
    skipped_questions   TEXT NOT NULL DEFAULT '',  -- deixadas para depois
    perception          TEXT NOT NULL DEFAULT '',  -- percepcao do usuario
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_mocks_date ON mock_exams(date);

CREATE TABLE mock_exam_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mock_exam_id    INTEGER NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    discipline_id   INTEGER NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
    total           INTEGER NOT NULL DEFAULT 0,
    correct         INTEGER NOT NULL DEFAULT 0,
    wrong           INTEGER NOT NULL DEFAULT 0,
    percentage      REAL NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    UNIQUE (mock_exam_id, discipline_id)
);
CREATE INDEX idx_mock_results_exam ON mock_exam_results(mock_exam_id);

CREATE TABLE taf_tests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    unit                TEXT NOT NULL DEFAULT '',   -- repeticoes | metros | segundos ...
    current_mark        REAL,
    goal_mark           REAL,
    higher_is_better    INTEGER NOT NULL DEFAULT 1, -- 0 quando menor e melhor (tempo)
    measured_at         TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    active              INTEGER NOT NULL DEFAULT 1,
    is_demo             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE taf_measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id     INTEGER NOT NULL REFERENCES taf_tests(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    value       REAL NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    is_demo     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_measurements_test ON taf_measurements(test_id, date);

CREATE TABLE taf_workouts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    name                TEXT NOT NULL DEFAULT '',
    type                TEXT NOT NULL DEFAULT 'corrida', -- corrida|forca|misto|outro
    duration_minutes    INTEGER NOT NULL DEFAULT 0,
    exercise            TEXT NOT NULL DEFAULT '',
    sets                INTEGER,
    reps                INTEGER,
    distance_km         REAL,
    time_text           TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'planejado', -- planejado|concluido|pendente
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_workouts_date ON taf_workouts(date, status);

CREATE TABLE college_subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    professor   TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    is_demo     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE college_tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    college_subject_id  INTEGER REFERENCES college_subjects(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    type                TEXT NOT NULL DEFAULT 'atividade', -- atividade|trabalho|prova|leitura
    due_date            TEXT,
    status              TEXT NOT NULL DEFAULT 'aberta',    -- aberta|concluida
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_college_tasks_due ON college_tasks(status, due_date);

CREATE TABLE college_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    college_subject_id  INTEGER REFERENCES college_subjects(id) ON DELETE SET NULL,
    minutes             INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_college_sessions_date ON college_sessions(date);
