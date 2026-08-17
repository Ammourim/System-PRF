-- Migration 004 - simplificacao radical: o sistema passa a responder duas
-- perguntas ("o que estudar hoje?" e "o que revisar hoje?").
--
-- Filosofia desta migration:
--   * NADA e apagado. Nenhuma tabela e removida, nenhuma coluna e derrubada.
--     As estruturas do ciclo antigo (cycle_blocks, target_minutes, block_minutes,
--     desired_blocks, min_blocks) continuam no banco e continuam funcionando -
--     apenas saem da interface principal.
--   * Somente duas colunas novas, ambas com valor padrao seguro.

-- 1. Frequencia: quantos dias por semana a disciplina aparece nos objetivos ----
--    0 = "deduza da prioridade" (maxima 5, alta 3, media 2, baixa 1).
--    Isso mantem qualquer disciplina criada depois funcionando sem edicao.
ALTER TABLE disciplines ADD COLUMN frequency INTEGER NOT NULL DEFAULT 0;

UPDATE disciplines SET frequency = CASE priority
        WHEN 'maxima' THEN 5
        WHEN 'alta'   THEN 3
        WHEN 'media'  THEN 2
        WHEN 'baixa'  THEN 1
        ELSE 2 END
 WHERE frequency <= 0;

-- 2. Conclusao do assunto: o marco que inicia a revisao espacada -------------
--    Registrar estudo NAO conclui o assunto. Somente o usuario declara isso, e
--    a data real da declaracao fica gravada aqui.
ALTER TABLE subjects ADD COLUMN completed_at TEXT;

-- Assunto que ja tem revisao agendada foi, na pratica, concluido no dia em que
-- a revisao nasceu. Recupera a data em vez de perder a informacao.
UPDATE subjects
   SET completed_at = (SELECT MIN(r.origin_date) FROM reviews r
                        WHERE r.subject_id = subjects.id)
 WHERE completed_at IS NULL
   AND EXISTS (SELECT 1 FROM reviews r WHERE r.subject_id = subjects.id);

-- Vocabulario de status do assunto: nao_iniciada | em_andamento | concluida.
-- 'revisao' e 'consolidada' eram, os dois, "assunto terminado".
UPDATE subjects SET status = 'concluida'
 WHERE status IN ('revisao', 'consolidada') OR completed_at IS NOT NULL;
