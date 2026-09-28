-- Migration 008 - o prazo da faculdade passa a ser a DATA DA PROVA, por disciplina.
--
-- Ate aqui existia um prazo unico (`college_deadline`) para toda a faculdade.
-- A realidade do semestre e outra: as provas caem em datas diferentes, e o
-- conteudo de cada disciplina precisa estar pronto na SUA data - adiantar LPS
-- para a data da prova de NoSQL so rouba tempo de quem tem prova antes.
--
-- Por isso a data vira coluna da disciplina. `college_deadline` continua valendo
-- como reserva, para disciplina cadastrada sem data.
--
-- As datas abaixo sao as deste semestre (provas de 19 e 23/11). Depois delas,
-- a data se edita na tela da faculdade - nenhuma migration nova e necessaria.

ALTER TABLE college_subjects ADD COLUMN exam_date TEXT;

UPDATE college_subjects SET exam_date = '2026-11-19'
 WHERE name IN ('Banco de Dados NoSQL',
                'Programacao para Dispositivos Moveis em Android',
                'Desenvolvimento de Back-end');

UPDATE college_subjects SET exam_date = '2026-11-23'
 WHERE name IN ('Linhas de Produtos de Software',
                'Qualidade e Testes de Software');
