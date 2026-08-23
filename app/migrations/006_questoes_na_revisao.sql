-- Migration 006 - questoes resolvidas dentro da revisao.
--
-- Revisar fazendo questoes e o caso mais comum: o acerto da revisao e o dado
-- que diz se o assunto realmente ficou. Ate aqui esse numero so existia se o
-- usuario abrisse o modulo de questoes e registrasse de novo, a mao.
--
-- Somente aditiva: duas colunas na tabela `reviews`, ambas com default 0.
-- Nenhuma linha existente muda de comportamento (revisao sem questoes continua
-- valendo como revisao). O registro de acerto em si continua vivendo na tabela
-- `questions` (kind = 'revisao'), que ja alimenta desempenho, pontos fracos e
-- sugestoes adaptativas - as colunas abaixo sao o acumulado da propria fila,
-- para a tela da revisao mostrar o historico sem recalcular nada.

ALTER TABLE reviews ADD COLUMN questions_total   INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reviews ADD COLUMN questions_correct INTEGER NOT NULL DEFAULT 0;

-- Recupera o que ja existe: questoes marcadas como 'revisao' que caem no dia em
-- que a revisao daquele assunto foi concluida entram no acumulado da fila.
UPDATE reviews SET
    questions_total = COALESCE((
        SELECT SUM(q.total) FROM questions q
         WHERE q.kind = 'revisao' AND q.subject_id = reviews.subject_id
           AND q.date = reviews.last_done_at), 0),
    questions_correct = COALESCE((
        SELECT SUM(q.correct) FROM questions q
         WHERE q.kind = 'revisao' AND q.subject_id = reviews.subject_id
           AND q.date = reviews.last_done_at), 0)
 WHERE subject_id IS NOT NULL AND last_done_at IS NOT NULL;
