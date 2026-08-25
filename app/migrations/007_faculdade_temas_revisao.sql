-- Migration 007 - faculdade com temas, ciclo proprio e revisao espacada.
--
-- Ate aqui a faculdade era so tempo (college_sessions) e prazos
-- (college_tasks): o sistema sabia QUANTO foi estudado, nunca O QUE falta.
-- Com prazo fechado para terminar o conteudo, faltava a unidade de conteudo.
--
-- `college_topics` e o TEMA - a mesma ideia de `subjects` no lado PRF:
-- concluir o tema e o marco que inicia a revisao espacada, e a lista de temas
-- pendentes e o que o ciclo da faculdade percorre.
--
-- `college_reviews` e a fila de revisao da faculdade. Tabela separada de
-- `reviews` de proposito: `reviews.discipline_id` aponta para as disciplinas do
-- edital (NOT NULL) e a faculdade e independente do PRF - misturar as duas
-- filas contaminaria desempenho, pontos fracos e a tela HOJE.
--
-- Somente aditiva: duas tabelas novas e uma coluna opcional em college_sessions.

CREATE TABLE college_topics (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    college_subject_id  INTEGER NOT NULL REFERENCES college_subjects(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    position            INTEGER NOT NULL DEFAULT 0,  -- ordem dentro da disciplina
    status              TEXT NOT NULL DEFAULT 'pendente',  -- pendente|concluido
    planned_date        TEXT,                        -- data sugerida pelo plano
    completed_at        TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (college_subject_id, name)
);
CREATE INDEX idx_college_topics_plan ON college_topics(status, planned_date);

CREATE TABLE college_reviews (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    college_subject_id  INTEGER NOT NULL REFERENCES college_subjects(id) ON DELETE CASCADE,
    college_topic_id    INTEGER REFERENCES college_topics(id) ON DELETE CASCADE,
    title               TEXT NOT NULL DEFAULT '',
    origin_date         TEXT NOT NULL,
    next_date           TEXT NOT NULL,
    step                INTEGER NOT NULL DEFAULT 0,
    interval_days       INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'pendente',  -- pendente|concluida|arquivada
    last_done_at        TEXT,
    times_done          INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT '',
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_college_reviews_due ON college_reviews(status, next_date);

-- Registro de estudo passa a poder apontar o tema (opcional: registro solto
-- continua valendo, exatamente como antes).
ALTER TABLE college_sessions ADD COLUMN college_topic_id INTEGER
    REFERENCES college_topics(id) ON DELETE SET NULL;
