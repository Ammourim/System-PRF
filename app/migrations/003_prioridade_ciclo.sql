-- Migration 003 - prioridade com efeito real na montagem do ciclo.
--
-- Motivo (auditoria SYSTEM_CONTEXT.md, secoes 5.2 e 6):
--   * `priority` era campo morto: nao era lido na geracao do ciclo;
--   * o vocabulario antigo (maxima|base|complementar) nao expressava a fase de
--     preparacao (o que e prioridade ALTA x MEDIA x BAIXA neste momento);
--   * a ordem do ciclo saia do numero de blocos, nao da prioridade.
--
-- Esta migration nao remove nenhuma disciplina. Todas continuam cadastradas e
-- ativas; muda apenas a prioridade e a meta declarada.

-- 1. Controle manual explicito da frequencia -------------------------------
--    desired_blocks > 0 -> o usuario fixou quantos blocos a disciplina recebe
--                          (vence o calculo automatico).
--    min_blocks    > 0 -> contato minimo garantido, mesmo com meta 0
--                          (usado para disciplina "nao iniciada" que nao deve
--                           ficar esquecida para sempre).
ALTER TABLE disciplines ADD COLUMN desired_blocks INTEGER NOT NULL DEFAULT 0;
ALTER TABLE disciplines ADD COLUMN min_blocks     INTEGER NOT NULL DEFAULT 0;

-- 2. Vocabulario de prioridade: 4 niveis -----------------------------------
--    maxima | alta | media | baixa
UPDATE disciplines SET priority = 'alta'  WHERE priority = 'base';
UPDATE disciplines SET priority = 'media' WHERE priority = 'complementar';
UPDATE disciplines SET priority = 'alta'
 WHERE priority NOT IN ('maxima', 'alta', 'media', 'baixa');

-- 3. Prioridades desta fase de preparacao ----------------------------------
UPDATE disciplines SET priority = 'maxima'
 WHERE short_name IN ('CTB', 'Portugues');

UPDATE disciplines SET priority = 'alta'
 WHERE short_name IN ('Administrativo', 'Constitucional', 'Informatica', 'RLM',
                      'Leg. Especial', 'Etica');

UPDATE disciplines SET priority = 'media'
 WHERE short_name IN ('Penal', 'Processo Penal');

UPDATE disciplines SET priority = 'baixa'
 WHERE short_name IN ('Espanhol', 'Dir. Humanos', 'Geopolitica', 'Fisica');

-- 4. Metas alinhadas a 1800 min (30h) por ciclo de 14 dias ------------------
--    Antes: soma das metas = 1785 e o plano gerado = 1875 (+75 sem aviso), com
--    disciplinas distorcidas em ate +-33% pelo arredondamento.
--    Agora: meta x bloco fecham em numero inteiro de blocos, sem residuo.
--    450 + 270 + (6 x 120) + (2 x 90) + (4 x 45) = 1800
UPDATE disciplines SET target_minutes = 450, block_minutes = 90 WHERE short_name = 'CTB';
UPDATE disciplines SET target_minutes = 270, block_minutes = 90 WHERE short_name = 'Portugues';

UPDATE disciplines SET target_minutes = 120, block_minutes = 60
 WHERE short_name IN ('Administrativo', 'Constitucional', 'Informatica', 'RLM',
                      'Leg. Especial', 'Etica');

UPDATE disciplines SET target_minutes = 90, block_minutes = 90
 WHERE short_name IN ('Penal', 'Processo Penal');

-- Prioridade baixa: contato minimo de 1 bloco por ciclo, nao exclusao.
UPDATE disciplines SET target_minutes = 45, block_minutes = 45, min_blocks = 1
 WHERE short_name IN ('Espanhol', 'Dir. Humanos', 'Geopolitica', 'Fisica');
