-- Migration 005 - o ciclo volta a ser uma SEQUENCIA com posicao.
--
-- Nao ha mudanca de estrutura aqui: nenhuma tabela, coluna ou registro e
-- criado ou removido. Sao apenas os tres campos que montam o ciclo
-- (priority, frequency, active) sendo ajustados para a configuracao atual da
-- preparacao. Historico de estudos, questoes, assuntos e revisoes ficam
-- intactos - inclusive os das disciplinas que ficam inativas.

-- 1. Prioridade: importancia da disciplina (define a ORDEM na sequencia) -----
UPDATE disciplines SET priority = 'maxima'
 WHERE short_name IN ('CTB', 'Portugues');

UPDATE disciplines SET priority = 'alta'
 WHERE short_name IN ('Administrativo', 'Constitucional', 'Informatica', 'RLM',
                      'Leg. Especial', 'Etica');

UPDATE disciplines SET priority = 'media'
 WHERE short_name IN ('Penal', 'Processo Penal');

UPDATE disciplines SET priority = 'baixa'
 WHERE short_name IN ('Espanhol', 'Dir. Humanos', 'Geopolitica', 'Fisica');

-- 2. Frequencia: quantas vezes a disciplina aparece em uma volta do ciclo ----
--    Prioridade nao multiplica ninguem: quem aparece 3x e quem esta com 3.
UPDATE disciplines SET frequency = 3 WHERE short_name = 'CTB';
UPDATE disciplines SET frequency = 2 WHERE short_name = 'Portugues';

UPDATE disciplines SET frequency = 1
 WHERE short_name IN ('Administrativo', 'Constitucional', 'Informatica', 'RLM',
                      'Leg. Especial', 'Etica', 'Penal', 'Processo Penal');

-- 3. Fora do ciclo POR ENQUANTO --------------------------------------------
--    Continuam cadastradas, com todo o historico. Basta marcar "Ativa" na tela
--    de Disciplinas para qualquer uma delas voltar a sequencia.
UPDATE disciplines SET active = 0, frequency = 1
 WHERE short_name IN ('Espanhol', 'Dir. Humanos', 'Geopolitica', 'Fisica');

-- 4. Posicao do ciclo: comeca na primeira disciplina da sequencia -----------
--    So avanca quando um estudo e concluido. Nunca por data.
INSERT INTO settings (key, value) VALUES ('cycle_position', '0')
    ON CONFLICT(key) DO UPDATE SET value = '0';

-- Chave do modelo anterior (teto de disciplinas por dia) deixa de ter uso.
DELETE FROM settings WHERE key = 'today_max_disciplines';
