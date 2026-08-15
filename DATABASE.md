# Banco de dados

SQLite unico em `data/prf.db`. Criado e evoluido por migrations em `app/migrations/*.sql`,
aplicadas em ordem alfabetica e registradas em `schema_migrations`. `PRAGMA foreign_keys`
sempre ligado; `journal_mode = WAL`.

## Convencoes

* Datas em **TEXT ISO** (`YYYY-MM-DD`) - ordenam corretamente como string no SQLite.
* Duracoes sempre em **minutos inteiros**. Nunca horas fracionadas.
* `is_demo = 1` marca registro de demonstracao (removivel em Configuracoes).
* Percentuais gravados como `REAL` ja calculados (`acertos / total * 100`, 2 casas), para
  permitir filtro e ordenacao por percentual sem recalcular.

## Tabelas

### `settings`
Chave/valor de toda configuracao (`key` PK, `value`, `updated_at`). Os padroes vivem em
`app/services/settings.py::DEFAULTS` e so sao gravados na primeira execucao. Chaves:
metas do ciclo, tamanhos de bloco, disponibilidade 12x36, intervalos de revisao,
frequencia de simulado, TAF, faculdade, limiares de desempenho e mix de questoes.

### `disciplines`
As 14 disciplinas. `incidence` (% historica), `priority` (`maxima|base|complementar`),
`status` (`nao_iniciada|em_andamento|revisao|consolidada`), `block_minutes` (tamanho
padrao do bloco), `target_minutes` (meta por ciclo), `active`, `is_demo`.
Editar peso, prioridade e meta e o caminho para adaptar o sistema ao edital novo.

### `subjects`
Assuntos de uma disciplina. `UNIQUE (discipline_id, name)` impede duplicata quando o
assunto e digitado direto no formulario de registro.

### `study_cycles`
Um ciclo. `number`, `start_date`, `end_date`, `days`, `goal_minutes`, `goal_questions`,
`current_position` (**a posicao atual no ciclo**) e `status` (`ativo|encerrado`).

### `cycle_blocks`
Os blocos ordenados do ciclo: `position`, `discipline_id`, `subject_id` (opcional),
`planned_minutes`, `block_size` (`longo|medio|curto|custom`), `focus`, `done`, `done_at`.
Indice `(cycle_id, position)`.

### `study_sessions`
Cada sessao registrada. `date`, `discipline_id`, `subject_id`, `type`
(`teoria|questoes|revisao|simulado|correcao_simulado|redacao|outro`), `planned_minutes`,
`actual_minutes`, `notes`, `completed`, `cycle_id`, `block_id`.
Indices em `date`, `discipline_id` e `cycle_id`.

### `questions`
Registro de questoes: `total`, `correct`, `wrong`, `percentage`, `banca`, `source`,
`kind` (`novo|revisao`), `notes` e `session_id` (preenchido quando as questoes foram
lancadas junto com a sessao). Indices em `date`, `discipline_id` e `subject_id`.

### `mistakes`
Caderno de erros. `category` (`C|E|I|A|D|CH`), `explanation`, `needs_review`,
`status` (`aberto|revisado|consolidado`) e `mock_exam_id` quando o erro veio de um simulado.

### `reviews`
Fila de revisao espacada. `origin_date`, `next_date`, `step` (indice na lista de
intervalos), `interval_days`, `difficulty`, `method`
(`questoes|flashcards|recuperacao_ativa|releitura|caderno_erros|mista`),
`status` (`pendente|concluida|arquivada`), `last_done_at`, `times_done`.
Indice `(status, next_date)` - e a consulta mais frequente do sistema.

### `mock_exams` e `mock_exam_results`
Simulado e desempenho por disciplina. O simulado guarda tambem a **estrategia de prova**:
`slow_questions`, `guessed_questions`, `skipped_questions`, `time_left_minutes` e
`perception`. `mock_exam_results` tem `UNIQUE (mock_exam_id, discipline_id)`, entao lancar
a mesma disciplina duas vezes atualiza em vez de duplicar.

### `taf_tests`, `taf_measurements`, `taf_workouts`
Testes do TAF com `unit`, `current_mark`, `goal_mark` e `higher_is_better` (0 quando menor
e melhor, como tempo de corrida); o historico de marcas; e os treinos planejados
(`status`: `planejado|concluido|pendente`).

### `college_subjects`, `college_tasks`, `college_sessions`
Faculdade, com planejamento independente do ciclo PRF.

## Diagrama de relacoes

```text
disciplines ──< subjects
     │              │
     ├──< cycle_blocks >── study_cycles
     ├──< study_sessions >── questions
     ├──< mistakes >── mock_exams ──< mock_exam_results
     └──< reviews

taf_tests ──< taf_measurements          college_subjects ──< college_tasks
taf_workouts (independente)                              └──< college_sessions
```

## Criando uma migration

1. Crie `app/migrations/002_descricao.sql`.
2. Escreva apenas o delta (`ALTER TABLE ...`, `CREATE INDEX ...`).
3. Reinicie o app - a migration e aplicada e registrada automaticamente.

Nao edite `001_initial.sql` depois que o banco ja existe: ele nao roda de novo.
Gere um backup antes de qualquer migration que altere dados.
