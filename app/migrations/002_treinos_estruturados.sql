-- Migration 002 - treino deixa de ser um registro unico e vira uma estrutura:
--
--   TREINO (plano)            taf_workouts
--     +-- EXERCICIO           taf_workout_exercises      (prescricao)
--   EXECUCAO (sessao)         taf_workout_sessions
--     +-- EXERCICIO EXECUTADO taf_session_exercises      (copia da prescricao)
--           +-- SERIE         taf_session_sets           (resultado real)
--
-- Decisoes:
--   * o treino vira um PLANO reutilizavel com vigencia, em vez de um agendamento
--     unico; cada realizacao passa a ser uma sessao com historico proprio;
--   * a sessao COPIA a prescricao. Editar ou apagar o plano depois nao reescreve
--     nem apaga o que ja foi executado;
--   * nenhum dado antigo e descartado: cada linha da tabela anterior vira um
--     plano + um exercicio, e as que estavam concluidas viram tambem uma sessao.

-- --------------------------------------------------------------------------
-- 1. Plano de treino (reconstroi taf_workouts; nada aponta para ela por FK)
-- --------------------------------------------------------------------------
ALTER TABLE taf_workouts RENAME TO taf_workouts_legacy;

CREATE TABLE taf_workouts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    objective           TEXT NOT NULL DEFAULT '',
    type                TEXT NOT NULL DEFAULT 'forca',
                        -- corrida|caminhada|forca|calistenia|core|mobilidade|
                        -- intervalado|misto|outro  (texto livre: aceita novas)
    duration_minutes    INTEGER NOT NULL DEFAULT 0,   -- duracao prevista
    start_date          TEXT,                          -- vigencia (inicio)
    end_date            TEXT,                          -- vigencia (fim, opcional)
    status              TEXT NOT NULL DEFAULT 'ativo', -- ativo | arquivado
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_workouts_status ON taf_workouts(status, start_date);

-- --------------------------------------------------------------------------
-- 2. Exercicios do plano (prescricao)
-- --------------------------------------------------------------------------
CREATE TABLE taf_workout_exercises (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id      INTEGER NOT NULL REFERENCES taf_workouts(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 1,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'forca',
    -- Prescricao: tudo opcional. Cada tipo de exercicio usa o que faz sentido.
    sets            INTEGER,            -- series
    reps            INTEGER,            -- repeticoes por serie
    seconds_per_set INTEGER,            -- tempo por serie (prancha, isometria)
    distance_km     REAL,               -- distancia (corrida, caminhada)
    total_seconds   INTEGER,            -- tempo total previsto
    rest_seconds    INTEGER,            -- descanso entre series
    goal            TEXT NOT NULL DEFAULT '',   -- meta em texto livre
    notes           TEXT NOT NULL DEFAULT '',
    is_demo         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_workout_exercises ON taf_workout_exercises(workout_id, position);

-- --------------------------------------------------------------------------
-- 3. Execucao do treino (sessao)
-- --------------------------------------------------------------------------
CREATE TABLE taf_workout_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id      INTEGER REFERENCES taf_workouts(id) ON DELETE SET NULL,
    workout_name    TEXT NOT NULL DEFAULT '',   -- copia: sobrevive a exclusao do plano
    date            TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'em_andamento',
                    -- em_andamento | concluida | abandonada
    notes           TEXT NOT NULL DEFAULT '',
    is_demo         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_sessions_date ON taf_workout_sessions(date, status);
CREATE INDEX idx_taf_sessions_workout ON taf_workout_sessions(workout_id);

-- --------------------------------------------------------------------------
-- 4. Exercicio dentro da execucao (copia da prescricao no momento do inicio)
-- --------------------------------------------------------------------------
CREATE TABLE taf_session_exercises (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL REFERENCES taf_workout_sessions(id) ON DELETE CASCADE,
    workout_exercise_id INTEGER REFERENCES taf_workout_exercises(id) ON DELETE SET NULL,
    position            INTEGER NOT NULL DEFAULT 1,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'forca',
    planned_sets        INTEGER,
    planned_reps        INTEGER,
    planned_seconds     INTEGER,
    planned_distance_km REAL,
    rest_seconds        INTEGER,
    goal                TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pendente',
                        -- pendente | concluido | pulado
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_taf_session_exercises ON taf_session_exercises(session_id, position);

-- --------------------------------------------------------------------------
-- 5. Serie realizada (o resultado de verdade)
-- --------------------------------------------------------------------------
CREATE TABLE taf_session_sets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_exercise_id INTEGER NOT NULL REFERENCES taf_session_exercises(id) ON DELETE CASCADE,
    set_number          INTEGER NOT NULL,
    reps                INTEGER,
    seconds             INTEGER,
    distance_km         REAL,
    notes               TEXT NOT NULL DEFAULT '',
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now')),
    is_demo             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (session_exercise_id, set_number)
);
CREATE INDEX idx_taf_session_sets ON taf_session_sets(session_exercise_id, set_number);

-- --------------------------------------------------------------------------
-- 6. Migracao dos dados antigos
-- --------------------------------------------------------------------------
-- Cada treino antigo vira um plano. A data unica que existia passa a ser a
-- vigencia (inicio e fim no mesmo dia), preservando quando ele foi planejado.
INSERT INTO taf_workouts (id, name, objective, type, duration_minutes, start_date,
                          end_date, status, notes, is_demo)
SELECT id,
       CASE WHEN TRIM(name) = '' THEN 'Treino ' || id ELSE name END,
       '',
       type,
       duration_minutes,
       date,
       date,
       'ativo',
       notes,
       is_demo
FROM taf_workouts_legacy;

-- Os campos de exercicio que ficavam soltos no treino viram o exercicio 1.
INSERT INTO taf_workout_exercises (workout_id, position, name, category, sets, reps,
                                   distance_km, rest_seconds, goal, notes, is_demo)
SELECT id,
       1,
       CASE WHEN TRIM(exercise) = '' THEN type ELSE exercise END,
       type,
       sets,
       reps,
       distance_km,
       NULL,
       COALESCE(time_text, ''),
       '',
       is_demo
FROM taf_workouts_legacy
WHERE TRIM(exercise) <> '' OR sets IS NOT NULL OR reps IS NOT NULL
   OR distance_km IS NOT NULL OR TRIM(COALESCE(time_text, '')) <> '';

-- Treinos que ja estavam concluidos viram uma sessao concluida, para que o
-- historico e a contagem no relatorio de ciclo continuem corretos.
INSERT INTO taf_workout_sessions (workout_id, workout_name, date, started_at,
                                  finished_at, duration_minutes, status, notes, is_demo)
SELECT id,
       CASE WHEN TRIM(name) = '' THEN 'Treino ' || id ELSE name END,
       date,
       date,
       date,
       duration_minutes,
       'concluida',
       notes,
       is_demo
FROM taf_workouts_legacy
WHERE status = 'concluido';

DROP TABLE taf_workouts_legacy;
