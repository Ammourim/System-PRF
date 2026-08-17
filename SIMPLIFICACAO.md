# Simplificacao radical - analise e o que mudou

O sistema passou a responder duas perguntas e mais nada:

    "Alan, o que voce precisa estudar hoje?"
    "Alan, quais assuntos voce precisa revisar hoje?"

A revisao espacada e o coracao. O ciclo virou apenas uma regra simples de
frequencia. O assunto e texto livre, e a revisao so comeca quando voce declara
"terminei este assunto".

---

## 1. Analise do codigo antes de mexer

### Modulos que sairam da experiencia principal

| Modulo | O que era | O que virou |
|---|---|---|
| Ciclo (`cycles`, `services/cycle.py`) | 594 linhas: blocos, `target_minutes`, `desired_blocks`, `min_blocks`, tolerancia, `split_minutes`, `spread`, previsao de horas | Fora do menu principal (agora em "Avancado > Ciclo detalhado"). Codigo intacto, nada quebrou |
| Painel antigo (`dashboard/index.html`) | 392 linhas, 9 cards: proximo bloco, aviso de simulado, desempenho 30 dias, pontos fracos, sequencia do ciclo, faculdade, TAF | Tela HOJE com 4 blocos: revisoes, objetivos, assuntos em andamento, resumo |
| Simulados | Aviso ocupava a tela inicial | Modulo mantido, aviso vive so em `/simulados/` |
| Desempenho / Sugestoes adaptativas | Item de menu de primeiro nivel | Mantidos, movidos para "Avancado" |
| TAF / Treinos / Faculdade | Misturados no painel do PRF | Mantidos, em "Fora do PRF" |
| Dificuldade da revisao (facil/media/dificil com fatores 1.5 / 0.6) | Multiplicava o intervalo | **Removido do calculo.** A conta agora e literal: conclusao + intervalo |

### Modulos que continuam sendo o sistema

`disciplines` (prioridade + frequencia), `reviews` (a fila), o registro de estudo
(agora em `/estudar`), `settings`, `data` (backup/export).

### Incompatibilidades com a nova filosofia (e o que foi feito)

| Incompatibilidade | Resolucao |
|---|---|
| O ciclo decidia o dia por posicao de bloco e minutos | Trocado por frequencia (dias por semana), sem minutos |
| Registrar estudo podia "agendar revisao" na mesma acao, confundindo estudo com conclusao | Separado: estudo nunca conclui assunto; a revisao nasce do "terminei este assunto" |
| A fila de revisao nunca terminava (repetia o maior intervalo para sempre) | Depois do ultimo intervalo o assunto e consolidado e sai da fila |
| Assunto exigia cadastro previo em varios fluxos | Campo de texto livre com sugestoes; cria na hora, sem duplicar |
| Status de assunto usava o vocabulario de disciplina (4 estados) | Assunto tem 3: nao iniciado / em andamento / concluido |

### Tabelas

- **Nucleo:** `disciplines`, `subjects`, `study_sessions`, `reviews`.
- **Opcionais mantidas:** `questions`, `mistakes`, `mock_exams`, `mock_exam_results`,
  `taf_*`, `college_*`.
- **Legado mantido (usadas so na tela "Ciclo detalhado"):** `study_cycles`, `cycle_blocks`.

**Nada foi apagado.** Nenhuma tabela removida, nenhuma coluna derrubada, nenhum
registro excluido. Backup gerado antes de tudo em `backups/`.

---

## 2. O que foi implementado

### Migration `004_simplificacao.sql` (somente aditiva)

- `disciplines.frequency` - dias por semana (0 = deduzir da prioridade);
- `subjects.completed_at` - a data real em que voce declarou o fim do assunto;
- assuntos que ja tinham revisao receberam `completed_at` recuperado da revisao,
  e o status virou `concluida` (antes: `revisao`/`consolidada`).

### Como o sistema escolhe a disciplina (revisado na migration 005)

O ciclo e uma **sequencia** com uma **posicao**. A tela HOJE mostra a disciplina
da vez - uma so.

  * **frequencia** = quantas vezes a disciplina aparece em uma volta do ciclo;
  * **prioridade** = a ordem, nunca a quantidade;
  * **inativa** = fora do ciclo, com o historico preservado.

Configuracao atual: CTB 3x, Portugues 2x, as outras oito ativas 1x; Espanhol,
Direitos Humanos, Geopolitica e Fisica inativas. Sequencia resultante:

    CTB, Portugues, Administrativo, Constitucional, CTB, Informatica, RLM,
    Portugues, Leg. Especial, CTB, Etica, Penal, Processo Penal

A posicao avanca **so** quando um estudo e concluido. Abrir o formulario e
desistir nao avanca. Nao estudar hoje nao avanca: amanha voce continua na mesma
disciplina. Nao existe agenda nem calendario.

### Fluxo diario

```
abrir o sistema
  -> REVISOES DE HOJE  (vermelho quando atrasada)  -> [ REVISAR ] -> [ CONCLUIR REVISAO ]
  -> ESTUDAR           (objetivos do dia)          -> [ ESTUDAR ] -> assunto + tempo + obs
                                                                    (tempo e obs opcionais)
  -> ASSUNTOS EM ANDAMENTO -> [ Terminei este assunto ]
        -> "Deseja agendar as revisoes espacadas?"  [ SIM ] [ NAO ]
        -> SIM: cria D1; ao concluir cada uma, agenda a seguinte
```

### Revisao espacada

- Sequencia configuravel em Configuracoes (padrao `1,7,15,30,60`);
- proxima data = **data real da conclusao** + proximo intervalo;
- atraso nao duplica nada: a mesma linha continua vencida, mostrando
  "Atrasada ha N dias";
- concluir a ultima (D60) consolida o assunto e encerra a sequencia;
- concluir o mesmo assunto duas vezes nao cria duas filas.

### Rotas novas

| Rota | O que faz |
|---|---|
| `GET /` | Tela HOJE |
| `GET/POST /estudar` | Formulario curto de registro de estudo |
| `POST /assunto/<id>/concluir` | Conclui o assunto (e pergunta sobre as revisoes) |
| `GET /assunto/<id>/revisoes` | A pergunta SIM / NAO |
| `POST /assunto/<id>/reabrir` | Desfaz a conclusao |
| `GET /revisoes/<id>` | Tela da revisao, com um botao |

---

## 3. O que continua igual

- Historico de estudos, questoes, caderno de erros, simulados, TAF, treinos e
  faculdade: mesmas telas, mesmas rotas, agora em menus secundarios;
- ciclo antigo com blocos e metas: intacto em "Avancado > Ciclo detalhado";
- backup e exportacao: sem alteracao;
- Espanhol continua cadastrado, prioridade baixa, sem nenhuma regra especifica -
  a prioridade e generica e vale para qualquer disciplina.

## 4. Testes

`191 testes passando`, incluindo `tests/test_today.py`, que fixa a filosofia:
abrir a tela nao cria nada, registrar estudo nao conclui assunto, concluir
assunto inicia a revisao, revisao atrasada conta da conclusao real, a sequencia
termina no ultimo intervalo e um dia sem estudo nao gera pendencia.
