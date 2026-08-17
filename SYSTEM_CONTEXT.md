# SYSTEM_CONTEXT.md — Sistema PRF

> Documento de auditoria técnica gerado por análise estática do código + inspeção do banco
> real (`data/prf.db`). Nenhum arquivo do projeto foi alterado.
> Data da análise: 2026-08-17. Versão da app: `1.0.0` (`app/__init__.py`).
> Referências no formato `arquivo:linha`.

---

## 1. STACK

| Item | Valor |
|---|---|
| Linguagem | Python 3 (usa `zoneinfo`, `X \| None`, `from __future__ import annotations`) |
| Framework backend | Flask 3.1.3 |
| Framework frontend | **Nenhum**. Jinja2 (server-side rendering) + CSS puro + ~132 linhas de JS vanilla |
| Banco de dados | SQLite 3 (arquivo único, `data/prf.db`), acesso via `sqlite3` da stdlib. **Sem ORM** |
| ORM / migrations | Nenhum ORM. Migrations = arquivos `.sql` numerados, aplicados em ordem alfabética e registrados em `schema_migrations` (`app/db.py:78-95`) |
| Bibliotecas | `Flask==3.1.3`, `tzdata==2026.3`, `pytest==9.1.1`. **Só isso** (`requirements.txt`). `werkzeug` (transitiva) para hash de senha |
| Gráficos | SVG gerado direto no template. Sem Chart.js/D3 |
| Autenticação | Usuário único, senha em hash no `.env` (`PRF_PASSWORD_HASH`), nunca no banco (`app/auth.py`) |
| Testes | pytest, 13 arquivos em `tests/` |
| Deploy alvo | PythonAnywhere (free tier), WSGI em `wsgi_pythonanywhere.py` |

### Como o projeto é executado

O banco é criado/migrado/populado **automaticamente** no `create_app()` (`app/__init__.py:24-33`).
Não existe passo manual obrigatório de setup.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements.txt
```

```bash
python run.py
```

Sobe em `http://127.0.0.1:5000` (configurável via `PRF_HOST` / `PRF_PORT`).

Comandos CLI adicionais (`app/db.py:130-200`):

```bash
flask --app run init-db
```
```bash
flask --app run seed-demo
```
```bash
flask --app run backup
```
```bash
flask --app run set-password
```

Utilitários (`scripts/`): `preview_cycle.py` (mostra a sequência do ciclo no terminal),
`importar_historico.py`, `backup_remoto.py` / `.bat`.

### Variáveis de ambiente (`app/config.py`)

`PRF_SECRET_KEY`, `PRF_PASSWORD_HASH`, `PRF_TIMEZONE` (default `America/Sao_Paulo`),
`PRF_DATABASE`, `PRF_BACKUP_DIR`, `PRF_EXPORT_DIR`, `PRF_HOST`, `PRF_PORT`, `PRF_DEBUG`,
`PRF_HTTPS`. Parser `.env` próprio, sem `python-dotenv`.

---

## 2. ESTRUTURA DO PROJETO

```
System-PRF/
├── run.py                        # entrypoint local
├── wsgi_pythonanywhere.py        # entrypoint de produção
├── requirements.txt
├── data/prf.db                   # banco SQLite (único arquivo de estado)
├── app/
│   ├── __init__.py               # create_app(): config, migrations, seed, filtros, blueprints, auth
│   ├── config.py                 # build_config() + parser .env próprio
│   ├── db.py                     # conexão sqlite, helpers query_*/execute/insert, migrations, backup/restore, CLI
│   ├── auth.py                   # login único, brute-force, CSRF por Origin, guard global before_request
│   ├── utils.py                  # datas com timezone, parsing de formulário, formatação, percentage()
│   ├── seed.py                   # ★ DISCIPLINAS HARDCODED + settings iniciais + 1º ciclo + dados demo
│   ├── migrations/
│   │   ├── 001_initial.sql       # 17 tabelas
│   │   └── 002_treinos_estruturados.sql  # reescreve TAF: plano→exercício→sessão→série
│   ├── services/                 # ★ toda a regra de negócio
│   │   ├── cycle.py              # ★ geração/ordenação de blocos, posição, avanço, progresso
│   │   ├── adaptive.py           # sugestões de ajuste de meta (nunca aplica sozinho)
│   │   ├── reviews.py            # revisão espaçada por lista de intervalos
│   │   ├── stats.py              # desempenho geral/disciplina/assunto/evolução/série diária
│   │   ├── mocks.py              # cálculo de "quando é o próximo simulado" + snooze
│   │   ├── settings.py           # ★ DEFAULTS + get/set de configurações
│   │   ├── workouts.py           # TAF: plano, prescrição, execução, séries (465 linhas)
│   │   └── dataio.py             # export CSV/JSON, import CSV com whitelist
│   ├── blueprints/               # camada HTTP (14 blueprints)
│   │   ├── common.py             # ★ constantes compartilhadas (tipos de sessão, categorias de erro, prioridades)
│   │   ├── dashboard.py  cycles.py  disciplines.py  sessions.py  questions.py
│   │   ├── mistakes.py   reviews.py  mocks.py  performance.py
│   │   ├── taf.py        workouts.py  college.py  settings.py  data.py
│   ├── templates/                # Jinja2, ~25 telas
│   └── static/{css/app.css, js/app.js}
├── scripts/
└── tests/                        # 13 arquivos pytest
```

### Responsabilidade dos módulos-chave

| Módulo | Responsabilidade |
|---|---|
| `services/cycle.py` | **Coração do sistema.** `spread()` distribui blocos, `plan_from_disciplines()` converte metas em nº de blocos, `advance()` move a posição, `progress()` calcula meta×realizado |
| `services/settings.py` | Fonte única de todo parâmetro configurável. `DEFAULTS` só é usado quando a chave nunca foi gravada |
| `services/adaptive.py` | Produz **sugestões** de mudança de `target_minutes` com justificativa textual. Nunca escreve no ciclo |
| `services/reviews.py` | Fila de revisão: cria, conclui (calcula próxima data), adia, arquiva |
| `services/stats.py` | Todas as agregações de desempenho. Consumido por dashboard, performance, adaptive, relatório de ciclo |
| `blueprints/common.py` | Dicionários de domínio (`SESSION_TYPES`, `MISTAKE_CATEGORIES`, `DISCIPLINE_STATUS`, `PRIORITIES`) + `resolve_subject()` (cria assunto ao digitar) |
| `seed.py` | Garante sistema utilizável no 1º start. **Contém as 14 disciplinas hardcoded** |
| `auth.py` | Guard global: recusa servir para host externo se não houver senha configurada |

---

## 3. BANCO DE DADOS

**22 tabelas** (17 da migration 001, +5 da 002, menos `taf_workouts` que foi reescrita) +
`schema_migrations`.

Convenções globais: datas ISO `YYYY-MM-DD` em `TEXT`; durações sempre em **minutos** (inteiro);
`is_demo = 1` marca registro removível de demonstração; `PRAGMA foreign_keys = ON`;
`journal_mode = WAL`.

### 3.1 `settings`
- **Finalidade:** todo parâmetro configurável do sistema (chave-valor, tudo em TEXT).
- **Campos:** `key` (PK), `value`, `updated_at`.
- **Relacionamentos:** nenhum. Lida por `services/settings.py`.

### 3.2 `disciplines`
- **Finalidade:** as matérias do edital PRF; a entidade que governa o ciclo.
- **Campos:** `id`, `name` (UNIQUE), `short_name`, `incidence` (REAL, % histórica — **é o "peso"**),
  `priority` (`maxima|base|complementar`), `status` (`nao_iniciada|em_andamento|revisao|consolidada`),
  `block_minutes` (tamanho padrão do bloco), `target_minutes` (**meta de minutos por ciclo — o que
  realmente gera blocos**), `position`, `active`, `notes`, `is_demo`.
- **Relacionamentos:** pai de `subjects`, `cycle_blocks`, `study_sessions`, `questions`,
  `mistakes`, `reviews`, `mock_exam_results`.
- **Índices:** só o PK + UNIQUE(name).

### 3.3 `subjects`
- **Finalidade:** assuntos dentro de uma disciplina (granularidade fina do desempenho).
- **Campos:** `id`, `discipline_id` (FK CASCADE), `name`, `status`, `notes`, `is_demo`.
- **Constraint:** `UNIQUE(discipline_id, name)`. **Índice:** `idx_subjects_discipline`.

### 3.4 `study_cycles`
- **Finalidade:** um ciclo de estudos; guarda a **posição atual** (o ponteiro do sistema).
- **Campos:** `id`, `number`, `name`, `start_date`, `end_date`, `days` (default 14),
  `goal_minutes` (1800), `goal_questions` (350), **`current_position`** (default 1),
  `status` (`ativo|encerrado`), `notes`, `is_demo`.
- **Índice:** `idx_cycles_status`.
- **Regra:** só existe **um** ciclo `ativo` por vez (garantido em código, não por constraint).

### 3.5 `cycle_blocks`
- **Finalidade:** cada bloco (unidade de estudo) da sequência do ciclo.
- **Campos:** `id`, `cycle_id` (FK CASCADE), **`position`** (ordem), `discipline_id` (FK CASCADE),
  `subject_id` (FK SET NULL, **sempre NULL na geração automática**), `planned_minutes`,
  `block_size` (`longo|medio|curto|custom`), `focus` (texto livre), `done`, `done_at`, `is_demo`.
- **Índice:** `idx_blocks_cycle(cycle_id, position)`.

### 3.6 `study_sessions`
- **Finalidade:** registro do que foi efetivamente estudado.
- **Campos:** `id`, `date`, `discipline_id` (SET NULL), `subject_id` (SET NULL),
  `type` (`teoria|questoes|revisao|simulado|correcao_simulado|redacao|outro`),
  `planned_minutes`, `actual_minutes`, `notes`, `completed`, `cycle_id` (SET NULL),
  `block_id` (SET NULL), `created_at`, `is_demo`.
- **Índices:** `date`, `discipline_id`, `cycle_id`.

### 3.7 `questions`
- **Finalidade:** lote de questões resolvidas (não é questão individual — é agregado).
- **Campos:** `id`, `date`, `discipline_id`, `subject_id`, `total`, `correct`, `wrong`,
  `percentage` (**desnormalizado, calculado na escrita**), `banca`, `source`,
  `kind` (`novo|revisao`), `notes`, `session_id` (SET NULL), `is_demo`.
- **Índices:** `date`, `discipline_id`, `subject_id`.

### 3.8 `mistakes` (caderno de erros)
- **Campos:** `id`, `date`, `discipline_id`, `subject_id`, `question_ref`,
  `category` (`C|E|I|A|D|CH`), `explanation`, `notes`, `needs_review`,
  `status` (`aberto|revisado|consolidado`), `mock_exam_id` (SET NULL), `is_demo`.
- **Índices:** `status`, `discipline_id`.

### 3.9 `reviews`
- **Campos:** `id`, `discipline_id` (CASCADE), `subject_id` (SET NULL), `title`, `origin_date`,
  **`next_date`**, `step` (índice na lista de intervalos), `interval_days`,
  `difficulty` (`facil|media|dificil`), `method`, `status` (`pendente|concluida|arquivada`),
  `last_done_at`, `times_done`, `notes`, `is_demo`.
- **Índices:** `idx_reviews_next(status, next_date)` — o índice que serve a fila do dashboard.

### 3.10 `mock_exams` / 3.11 `mock_exam_results`
- `mock_exams`: `name`, `date`, `banca`, `prova`, `total`, `correct`, `wrong`, `percentage`,
  `total_minutes`, `planned_minutes`, `time_left_minutes`, `slow_questions`,
  `guessed_questions`, `skipped_questions`, `perception`, `notes`. Índice em `date`.
- `mock_exam_results`: `mock_exam_id` (CASCADE), `discipline_id` (CASCADE), `total`, `correct`,
  `wrong`, `percentage`, `notes`. `UNIQUE(mock_exam_id, discipline_id)` → permite UPSERT.

### 3.12 `taf_tests` / 3.13 `taf_measurements`
- `taf_tests`: `name`, `unit`, `current_mark`, `goal_mark`, `higher_is_better`, `measured_at`,
  `active`.
- `taf_measurements`: `test_id` (CASCADE), `date`, `value`, `notes`.
  Índice `(test_id, date)`.

### 3.14–3.18 TAF estruturado (migration 002)
```
taf_workouts (plano)
  └── taf_workout_exercises (prescrição)
taf_workout_sessions (execução)
  └── taf_session_exercises (CÓPIA da prescrição)
        └── taf_session_sets (resultado real, UNIQUE(session_exercise_id, set_number))
```
- `taf_workouts`: `name`, `objective`, `type`, `duration_minutes`, `start_date`, `end_date`
  (vigência), `status` (`ativo|arquivado`), `created_at`, `updated_at`.
- `taf_workout_sessions.workout_id` é **SET NULL** e `workout_name` é copiado → apagar o plano
  não apaga o histórico.
- Índices: `(status,start_date)`, `(workout_id,position)`, `(date,status)`, `(workout_id)`,
  `(session_id,position)`, `(session_exercise_id,set_number)`.

### 3.19–3.21 Faculdade
- `college_subjects`: `name`, `professor`, `notes`, `active`.
- `college_tasks`: `college_subject_id` (SET NULL), `title`, `type`
  (`atividade|trabalho|prova|leitura`), `due_date`, `status` (`aberta|concluida`).
  Índice `(status, due_date)`.
- `college_sessions`: `date`, `college_subject_id` (SET NULL), `minutes`, `notes`.
  Índice em `date`.

---

## 4. MODELO DE DADOS — como tudo se relaciona

```
                          ┌───────────────┐
                          │  disciplines  │  incidence, priority, block_minutes, target_minutes
                          └───────┬───────┘
        ┌──────────────┬──────────┼──────────┬──────────────┬───────────────┐
        │              │          │          │              │               │
   ┌────▼────┐   ┌─────▼─────┐ ┌──▼──────┐ ┌─▼───────┐ ┌────▼─────┐ ┌───────▼────────┐
   │subjects │   │cycle_blocks│ │questions│ │mistakes │ │ reviews  │ │mock_exam_results│
   └────┬────┘   └─────┬──────┘ └────┬────┘ └────┬────┘ └──────────┘ └───────┬────────┘
        │              │             │           │                           │
        │        ┌─────▼──────┐      │           └──────► mock_exam_id ──────┤
        │        │study_cycles│      │                                       │
        │        └────────────┘      │                                 ┌─────▼─────┐
        └────────────────────────────┴───────────────────────────────► │mock_exams │
                       ▲                                               └───────────┘
                       │
                ┌──────┴────────┐
                │study_sessions │ ── block_id ─► cycle_blocks
                └───────────────┘ ── cycle_id ─► study_cycles

  ILHAS ISOLADAS (zero FK para disciplines/cycles):
    taf_tests → taf_measurements
    taf_workouts → taf_workout_exercises ; taf_workout_sessions → taf_session_exercises → taf_session_sets
    college_subjects → college_tasks , college_sessions
    settings (chave-valor, sem FK)
```

**Leitura das relações:**

- **disciplina → assunto:** 1:N, cascade. O assunto pode ser criado digitando no formulário
  (`common.resolve_subject`, `blueprints/common.py:62-81`).
- **disciplina → ciclo:** indireta. `disciplines.target_minutes` + `disciplines.block_minutes`
  geram N `cycle_blocks`. **Não existe tabela de "disciplinas do ciclo"** — o vínculo é só via
  bloco.
- **ciclo → bloco:** 1:N ordenado por `position`. O ciclo aponta para 1 bloco através de
  `current_position`.
- **bloco → sessão:** opcional (`study_sessions.block_id`). Uma sessão pode existir sem bloco e
  um bloco pode ser concluído sem sessão.
- **sessão → questões:** 0..1 (o código assume **uma** linha de `questions` por sessão —
  `blueprints/sessions.py:138`).
- **erro → revisão:** só por ação explícita (`mistakes.to_review`), que cria uma `review` nova e
  marca o erro como `revisado`. Não há FK entre eles.
- **simulado → erro:** `mistakes.mock_exam_id`.
- **simulado → disciplina:** via `mock_exam_results`; alimenta `adaptive.suggestions()`.
- **TAF, faculdade, configurações:** **completamente desacoplados** de disciplinas e do ciclo.
  Só aparecem juntos em telas de leitura (dashboard, relatório de ciclo).

---

## 5. CICLO DE ESTUDOS — funcionamento exato

Arquivo: `app/services/cycle.py`. Docstring declara a regra central:
*"o ciclo NÃO depende de calendário"* (`cycle.py:3-6`).

### 5.1 Como os blocos são criados

Duas rotas equivalentes:

1. **Automática (1º start):** `seed._ensure_first_cycle()` → busca disciplinas ativas ordenadas
   por `incidence DESC, position` → `plan_from_disciplines()` → `spread()` → INSERT em
   `cycle_blocks`.
2. **Manual:** tela `/ciclo/montar` (`blueprints/cycles.py:36-100`). O usuário edita
   `target_minutes` e `block_minutes` de cada disciplina; o POST **grava esses valores na tabela
   `disciplines`** e depois monta o plano.

Fórmula do número de blocos (`cycle.py:74`, duplicada em `cycles.py:55`):

```
count = max(1, int(target_minutes / block_minutes + 0.5))     # arredondamento "para o mais próximo"
```
Disciplina com `target_minutes = 0` é **excluída do ciclo** (`cycle.py:72`).

### 5.2 Como a ordem é definida — o algoritmo `spread()`

`cycle.py:20-63`. Não é uma ordem por prioridade; é uma **intercalação por posição relativa**:

1. Para cada disciplina com `k` blocos, o i-ésimo bloco (i de 0 a k-1) recebe a chave
   `key = (i + 0.5) / k`.
2. Ordena por `(key, -count, ordem_de_entrada)`.
3. `_separate_neighbours()` faz uma passada trocando blocos vizinhos iguais.

**Consequências diretas do algoritmo:**
- Uma disciplina com 2 blocos tem chaves `0.25` e `0.75`. Uma com 1 bloco tem chave `0.5`.
  → **toda disciplina com 2 blocos aparece antes de toda disciplina com 1 bloco**, mesmo que a de
  1 bloco tenha meta de minutos maior.
- Empates de chave são resolvidos por `ordem_de_entrada`, que vem de
  `disciplines() ORDER BY incidence DESC, name` — a incidência entra **só como desempate**.
- **`disciplines.priority` (`maxima|base|complementar`) NÃO é consultado em nenhum ponto da
  geração do ciclo.** Grep confirma: aparece apenas em `adaptive.py:77`, `stats.py:48` (SELECT) e
  nos CRUDs de disciplina.

### 5.3 Como o próximo bloco é identificado

```python
next_block() → block_at(cycle_id, cycle.current_position)     # cycle.py:172-177
```
É uma leitura direta: o bloco cuja `position` é igual a `current_position`. Não há busca por
"primeiro não concluído", nem por data.

### 5.4 Como o bloco é concluído / como o sistema avança

`advance()` (`cycle.py:192-210`) faz duas coisas:
```python
UPDATE cycle_blocks SET done = 1, done_at = hoje WHERE id = block_id   # se mark_done
UPDATE study_cycles SET current_position = min(current_position + 1, total + 1)
```
Sempre **+1**. Nunca "pula para hoje". Disparado por:
- botão "Concluir bloco" no dashboard/ciclo → `POST /ciclo/avancar`;
- checkbox `advance_cycle` no formulário de sessão (`sessions.py:173`);
- `POST /ciclo/posicao` (ajuste manual livre da posição);
- `toggle_block_done()` marca/desmarca `done` **sem** mexer na posição.

Quando `current_position > total_blocks`, `next_block()` retorna `None` e a tela mostra o painel
"ciclo concluído" com links para relatório e montar o próximo. **O ciclo não se encerra sozinho e
nenhum ciclo novo é criado automaticamente.**

### 5.5 O que acontece quando o usuário não estuda

**Nada.** Não há job, cron, nem verificação de data. A posição fica onde está. Não gera pendência,
não reinicia, não pune. É explicitamente uma decisão de projeto (`cycle.py:4-6`,
`ROADMAP.md` → "Não será feito: notificações ou jobs em segundo plano que alterem datas").

### 5.6 Dependência de calendário

Formalmente **não** — com uma exceção relevante:

`progress()` (`cycle.py:263-272`) soma minutos e questões **filtrando por
`date BETWEEN cycle.start_date AND cycle.end_date`**. `end_date` = `start_date + days - 1`
(14 dias por padrão). Ou seja: se o ciclo de 27 blocos levar 20 dias para ser concluído, os
estudos do 15º dia em diante **não aparecem no progresso do ciclo**, embora os blocos contem.
Blocos são calendário-independentes; métricas de progresso não são.

### 5.7 Como a duração dos blocos é calculada

`planned_minutes` do bloco = `disciplines.block_minutes` da disciplina, copiado direto
(`cycle.py:133`). Não há cálculo, distribuição proporcional, nem ajuste ao total.
`block_size` é apenas um rótulo derivado (`settings.block_size_name()`: 90→`longo`,
60→`medio`, 45→`curto`, resto→`custom`).

### 5.8 Distribuição das disciplinas e parâmetros que a influenciam

| Parâmetro | Onde vive | Efeito |
|---|---|---|
| `target_minutes` | `disciplines` | **Determina o nº de blocos.** Único fator de "quanto" |
| `block_minutes` | `disciplines` | Determina a duração do bloco e, junto com o target, o nº de blocos |
| `active` | `disciplines` | `active = 0` → fora do ciclo |
| `incidence` | `disciplines` | **Só desempate de ordem.** Não afeta quantidade |
| `priority` | `disciplines` | **Nenhum efeito no ciclo** |
| `status` | `disciplines` | **Nenhum efeito no ciclo** (afeta só as sugestões do adaptive) |
| `position` | `disciplines` | Usado apenas no seed inicial; a listagem ordena por incidência |
| `cycle_days`, `prf_goal_minutes`, `questions_goal_per_cycle` | `settings` | Metas do ciclo. **Não limitam nem escalam o plano** |

**Não existe algoritmo de distribuição por peso.** Não há normalização do total de minutos contra
`prf_goal_minutes` nem contra `estimated_capacity()`. Hoje o plano soma **1875 min** contra a meta
de **1800 min** e nada avisa.

---

## 6. PRIORIDADE DAS DISCIPLINAS — estado real do banco

Dados lidos de `data/prf.db` em 2026-08-17, ciclo ativo `Ciclo #01` (27 blocos, `current_position = 1`).

| Disciplina | Peso (incidence %) | Prioridade | Frequência (blocos/ciclo) | Horas previstas (blocos × block_min) | Meta declarada (`target_minutes`) | Está no ciclo? |
|---|---|---|---|---|---|---|
| Legislação de Trânsito (CTB) | 25,00 | maxima | 5 | 7h30 (450) | 450 | ✅ posições 1,10,12,18,27 |
| Língua Portuguesa | 15,00 | maxima | 3 | 4h30 (270) | 270 | ✅ 2,11,26 |
| **Espanhol** | **6,70** | **base** | **2** | **2h00 (120)** | **90** ⚠️ **+30** | ✅ **3**, 19 |
| Direito Administrativo | 5,80 | base | 1 | 1h30 (90) | 120 ⚠️ **−30** | ✅ 13 |
| Direito Constitucional | 5,80 | base | 1 | 1h30 (90) | 120 ⚠️ **−30** | ✅ 14 |
| Informática | 5,80 | base | 2 | 2h00 (120) | 120 | ✅ 4, 20 |
| RLM | 5,00 | base | 2 | 2h00 (120) | 120 | ✅ 7, 23 |
| Legislação Especial | 5,00 | base | 2 | 2h00 (120) | 105 ⚠️ +15 | ✅ 6, 22 |
| Ética e Cidadania | 5,00 | base | 2 | 2h00 (120) | 90 ⚠️ +30 | ✅ 5, 21 |
| Direito Penal | 4,20 | complementar | 2 | 2h00 (120) | 90 ⚠️ +30 | ✅ 8, 24 |
| Direito Processual Penal | 4,20 | complementar | 2 | 2h00 (120) | 90 ⚠️ +30 | ✅ 9, 25 |
| Direitos Humanos | 4,20 | complementar | 1 | 0h45 (45) | 60 ⚠️ −15 | ✅ 15 |
| Geopolítica | 4,20 | complementar | 1 | 0h45 (45) | 60 ⚠️ −15 | ✅ 16 |
| Física | 4,00 | complementar | 1 | 0h45 (45) | 60 ⚠️ −15 | ✅ 17 |
| **TOTAL** | 100,10 | — | **27 blocos** | **31h15 (1875 min)** | 1785 min | meta do ciclo: **1800** |

**Todas as 14 disciplinas estão ativas e todas entram no ciclo.** Nenhuma está fora.

Sequência real dos 27 blocos:
`CTB, Português, Espanhol, Informática, Ética, Leg.Especial, RLM, Penal, Proc.Penal, CTB,
Português, CTB, Administrativo, Constitucional, Dir.Humanos, Geopolítica, Física, CTB, Espanhol,
Informática, Ética, Leg.Especial, RLM, Penal, Proc.Penal, Português, CTB`

---

## 7. QUESTÕES

**Como são registradas** — dois caminhos, ambos gravam na mesma tabela `questions`:
1. Junto da sessão (`POST /sessoes/salvar`): campos `questions_total` / `questions_correct`.
   O sistema cria **ou atualiza** a linha ligada por `session_id` (`sessions.py:133-159`).
   `kind` é derivado: `revisao` se `session.type == 'revisao'`, senão `novo`.
2. Avulso (`POST /questoes/salvar`), sem sessão vinculada.

**Como acertos são calculados** — não são calculados; são **informados**. O sistema apenas
sanitiza: `correct = max(0, min(correct, total))` e `wrong = total - correct`.

**Como o percentual é calculado** — `utils.percentage(correct, total)`:
```python
round(correct / total * 100, 2)     # total == 0 → 0.0
```
Gravado **desnormalizado** na coluna `questions.percentage` no momento da escrita. As agregações
(`stats.by_discipline`, `overall`) **recalculam** a partir de `SUM(correct)/SUM(total)` e ignoram
a coluna — ou seja, a coluna só é usada para filtros (`min_pct`/`max_pct`) e exibição de linha.

**Como influenciam o desempenho** — são a **única** fonte de acurácia do sistema (junto com
simulados). Alimentam: `stats.overall`, `by_discipline`, `by_subject`, `weak_points`,
`weak_disciplines`, `evolution`, `daily_series`, `cycle.progress`.

**Como influenciam o ciclo** — **indiretamente e apenas com clique do usuário.**
`adaptive.suggestions()` lê a acurácia e propõe `target_minutes ± 30`. O usuário aplica uma
sugestão de cada vez em `/desempenho/ajustes/aplicar`. Isso muda `disciplines.target_minutes`,
mas o ciclo em curso **não muda** — só o próximo, ou se o usuário regenerar os blocos manualmente.
A mensagem de sucesso diz isso explicitamente (`performance.py:59`).

**Metas** — três, todas configuráveis:
| Meta | Chave | Valor atual | Onde aparece |
|---|---|---|---|
| Por ciclo | `questions_goal_per_cycle` | **350** | copiada para `study_cycles.goal_questions` na criação |
| Por dia de folga | `questions_goal_per_folga` | **50** | card "Hoje" do dashboard |
| Split sugerido | `questions_split_new` / `questions_split_review` | **30 / 20** | apenas exibido na tela de questões — **não é validado nem cobrado** |

`questions_pct = questions / goal_questions * 100` (`cycle.py:287`). A meta **não é derivada**
de nada — é um número digitado.

---

## 8. CADERNO DE ERROS

**Estrutura:** tabela `mistakes`, uma linha por erro. Campos-chave: `question_ref` (enunciado
curto/código), `category`, `explanation` (por que errou), `status`, `needs_review`,
`mock_exam_id` (se veio de simulado).

**Categorias** (`blueprints/common.py:22-29`, fixas no código):

| Código | Significado |
|---|---|
| `C` | Não conhecia o conteúdo |
| `E` | Esqueci |
| `I` | Interpretação |
| `A` | Atenção |
| `D` | Dúvida entre alternativas |
| `CH` | Chute |

**Como são registrados:**
- Manualmente em `/erros/salvar`;
- A partir de um simulado em `POST /simulados/<id>/erro` (herda a data do simulado e o
  `mock_exam_id`; **`subject_id` é forçado a NULL** nesse caminho — `mocks.py:174`).

**Como são revisados:** três mecanismos independentes:
1. Mudança manual de status: `aberto → revisado → consolidado` (`POST /erros/<id>/status`).
   Consolidados somem da listagem padrão.
2. Conversão em revisão: `POST /erros/<id>/revisar` cria uma `review` com
   `method = 'caderno_erros'`, `title` = os primeiros 80 chars do `question_ref`, `notes` = a
   explicação; e marca o erro como `revisado`.
3. Método `caderno_erros` numa revisão qualquer (apenas um rótulo — não puxa os erros).

**Influência no planejamento:** **nenhuma.** Os erros aparecem em `stats.mistakes_by_category()`
(gráfico por categoria em `/desempenho`) e na tela da disciplina. Não entram em
`adaptive.suggestions()`, não geram bloco, não alteram `target_minutes`, não criam revisão
automaticamente. O campo `needs_review` é gravado mas **nunca lido em nenhuma query**.

---

## 9. REVISÃO ESPAÇADA

Arquivo: `app/services/reviews.py`. A docstring é explícita: *"Decisão consciente: não há
algoritmo sofisticado (FSRS/SM-2) aqui."*

**Como uma revisão é criada** — sempre por ação explícita, quatro origens:
1. Checkbox `create_review` no formulário de sessão (`sessions.py:162-170`);
2. Formulário manual em `/revisoes/nova` (permite escolher o `first_interval`);
3. `POST /erros/<id>/revisar`;
4. Seed de demonstração.

`create_review()` grava `step = 0`, `interval_days = intervals()[0]` (=1),
`next_date = origin_date + interval`, `status = 'pendente'`.

**Quando aparece** — a fila é `status = 'pendente' AND next_date <= hoje`, ordenada por
`next_date, incidence DESC` (`reviews.py:125-139`). É rotulada:
`next_date < hoje` → `atrasada`; `== hoje` → `hoje`; `>` → `futura`.
Aparece no dashboard (6 itens), no badge da navegação (`review_badge`) e na tela `/revisoes/`.

**Intervalos utilizados** — `settings.review_intervals`, valor atual **`1,7,15,30,60`** (dias).
Editável na tela de Configurações. Fallback no código: `[1,7,15,30,60]` (`reviews.py:31`).
Depois do último passo, o **maior intervalo se repete indefinidamente** (`reviews.py:34-39`).

**Como é concluída** — `POST /revisoes/<id>/concluir` → `complete_review()`:
```python
next_step = step + 1
base     = interval_for_step(next_step)
factor   = 1.5 se 'facil' | 0.6 se 'dificil' | 1.0 se 'media'    # ambos configuráveis
interval = max(1, round(base * factor))
next_date = data_da_conclusao + interval
status = 'pendente'    # ← reagendada, NUNCA fica 'concluida'
times_done += 1 ; last_done_at = data
```
Opcionalmente registra uma `study_session` do tipo `revisao` com os minutos informados
(`reviews.py:70-80`).

**Existe algoritmo?** Sim, mas trivial e determinístico: índice na lista × fator de dificuldade.
Sem ease factor acumulado, sem histórico de acertos, sem penalidade por atraso. Uma revisão
atrasada 10 dias produz exatamente a mesma próxima data que uma feita em dia.

**Repetição espaçada automática?** A **reagendagem** é automática ao concluir. A **criação** nunca
é. Não há job em background. O valor `status = 'concluida'` existe no schema mas **nunca é
gravado** — a revisão só sai da fila via `arquivar`.

**O usuário pode alterar datas?** Sim, totalmente:
- `POST /revisoes/<id>/salvar` sobrescreve `next_date` e `interval_days` livremente;
- `POST /revisoes/<id>/adiar` (+N dias a partir de `max(next_date, hoje)`);
- `POST /revisoes/<id>/reativar` traz para hoje;
- `POST /revisoes/<id>/arquivar` / `excluir`.

---

## 10. SIMULADOS

**Cadastro** — `POST /simulados/salvar`. Campos: nome, data, banca, prova, total/acertos,
`total_minutes`, `planned_minutes`, `time_left_minutes`, e três listas de texto livre
(`slow_questions`, `guessed_questions`, `skipped_questions`) + `perception` + `notes`.
Há também `/simulados/cronometro` — modo "prova real", tela limpa sem navegação
(`templates/mocks/timer.html`, JS local; **o cronômetro não grava nada sozinho**).

**Resultados** — `percentage = percentage(correct, total)`, com `correct` limitado a `total`.
Opcionalmente (`recalc_total`) o total do simulado é **recalculado** somando os lançamentos por
disciplina (`mocks.py:150-157`).

**Desempenho por disciplina** — tabela `mock_exam_results`, UPSERT por
`(mock_exam_id, discipline_id)`. Na tela de detalhe, as disciplinas são separadas em `strong` /
`weak` pelo limiar `performance_mid` (**70%**), e é calculado `minutes_per_question` e o delta
contra o simulado anterior.

**Influência no ciclo** — **indireta, só via sugestões.** `mocks.last_results_by_discipline()`
retorna o desempenho do último simulado *que tenha lançamentos por disciplina*, e
`adaptive._reasons()` usa isso como **segundo sinal, de peso maior que a questão avulsa**:
- se há < 10 questões avulsas no período, o simulado vira o sinal **principal**;
- `mock_pct < performance_low` (60%) → força direção `aumentar`, mesmo que as questões avulsas
  estejam boas ("sinal de tempo/pressão, não de conteúdo");
- `mock_pct < performance_mid` (70%) **bloqueia** uma sugestão de `reduzir`;
- resultados com menos de `MIN_MOCK_QUESTIONS = 5` questões são ignorados.

Nada disso muda o ciclo sozinho — vira texto na tela `/desempenho/ajustes`.

**Tempo de prova** — três campos independentes em minutos, aceitos em formatos `300`, `5:00`,
`5h`, `5h30` (`utils.parse_minutes`). Não há validação de coerência entre eles
(`total_minutes + time_left_minutes` vs `planned_minutes`).

**Aviso de frequência** — `mocks.status()`. `mock_frequency` (atual: **quinzenal**) mapeia para
`{semanal:7, quinzenal:14, mensal:30, manual:None}` (**dicionário hardcoded**, `mocks.py:15`).
Estados: `manual | primeiro | vencido | hoje | agendado | adiado`. O aviso pode ser silenciado
(`mock_snooze_until`) sem alterar a frequência. **Nunca cria simulado, nunca insere bloco no
ciclo, nunca gera pendência.**

---

## 11. TAF

Dois módulos separados: **testes/marcas** (`blueprints/taf.py`) e **treinos**
(`blueprints/workouts.py` + `services/workouts.py`, 465 linhas).

**Testes e metas** — `taf_tests`: nome, unidade, `goal_mark`, `higher_is_better` (0 quando menor é
melhor, ex.: tempo). Seed cria 4 testes: Corrida 12 min (meta 2800 m), Barra fixa (10),
Flexão (30), Abdominal 1 min (40) — com a nota *"Meta de referência - ajustar quando o edital
sair"*. As metas são editáveis.

**Marcas** — `POST /taf/testes/<id>/marca` insere em `taf_measurements` e **automaticamente**
atualiza `taf_tests.current_mark`/`measured_at` com a medição de data mais recente.

**Treinos — estrutura (migration 002):**
```
PLANO      taf_workouts            nome, objetivo, tipo, duração prevista, vigência (start/end), status
  └ EXERCÍCIO  taf_workout_exercises   prescrição flexível: sets, reps, seconds_per_set,
                                       distance_km, total_seconds, rest_seconds, goal (texto)
EXECUÇÃO   taf_workout_sessions    data, started_at, finished_at, duration, status
  └ EXERC.   taf_session_exercises   CÓPIA da prescrição no momento do início
      └ SÉRIE  taf_session_sets        reps / seconds / distance_km reais, por série
```
`start_session()` copia a prescrição — editar ou apagar o plano depois **não reescreve o
histórico**. `finish_session()` calcula a duração pelo `started_at` (ou aceita minutos manuais) e
marca exercícios intocados como `pulado`.

**Evolução:**
- Por teste (`taf.py:32-44`):
  `delta = (última − primeira) / primeira × 100`, **invertido** se `higher_is_better = 0`.
  `progress = current/goal × 100` (ou `goal/current` quando menor é melhor), teto 999%.
- Por treino: `exercise_progress()` compara prescrito × realizado série a série.
- Volume: `minutes_in_period()` soma `duration_minutes` das sessões `concluida`.

**Interfere no ciclo PRF?** **Não.** Zero FK, zero leitura cruzada. Os únicos pontos de contato
são visuais/informativos:
- card "Hoje" do dashboard mostra a sessão de treino do dia;
- "Pendências fora do ciclo" mostra uma sessão `em_andamento` não encerrada — e a docstring do
  dashboard frisa: *"'Pendência' agora é um treino iniciado e não encerrado — não um dia perdido"*
  (`dashboard.py:27`);
- `taf_minutes_per_cycle` (**420 min**) é comparado contra os minutos dos últimos **14 dias fixos**
  (`add_days(today, -13)` hardcoded em `taf.py:56` — **não usa `cycle_days` nem as datas do ciclo**);
- `adaptive.cycle_report()` inclui a contagem de treinos do período, só para leitura.

---

## 12. FACULDADE

`blueprints/college.py`. Três tabelas independentes.

**Cadastro:** disciplinas (`nome`, `professor`, `active`), atividades
(`title`, `type ∈ {atividade, trabalho, prova, leitura}`, `due_date`, `status ∈ {aberta, concluida}`)
e sessões de estudo (`date`, `minutes`).

**Contabilização de horas:** `minutes_week = SUM(minutes) WHERE date >= inicio_da_semana`, com a
semana começando na **segunda-feira** (`_week_start`, `college.py:53-57`).
Meta: `college_hours_per_week` (**4h** → 240 min).
⚠️ A query filtra apenas `date >= week_start`, **sem limite superior** — registros com data futura
entram na conta da semana atual.

**Interfere no ciclo PRF?** **Não.** As horas de faculdade nunca são somadas às horas PRF
(`stats.today_summary` mantém `prf_minutes` e `college_minutes` separados). Contatos:
- card "Hoje" do dashboard (minutos de faculdade, meta semanal);
- "Pendências fora do ciclo": tarefas abertas com vencimento nos próximos 14 dias
  (`dashboard.py:31-34`, janela **hardcoded**);
- `cycle_report` mostra `college_minutes` do período.

---

## 13. DASHBOARD

Rota `/`, controller `blueprints/dashboard.py` (57 linhas), template
`templates/dashboard/index.html` (392 linhas).

| Elemento na tela | Origem do dado |
|---|---|
| Subtítulo: data + nome/período do ciclo | `utils.today_iso()` + `cycle_service.active_cycle()` |
| **Próximo bloco** (disciplina, assunto, minutos, tamanho, foco) + "posição X de Y" | `cycle_service.next_block()` + `progress.position` / `progress.total_blocks` |
| Painel "ciclo concluído" (quando `position > total`) | `block is None` e `cycle` presente |
| Painel "montar ciclo" (quando não há ciclo ativo) | `cycle is None` |
| **Simulado recomendado** (estado, dias desde o último, dias de atraso, botões fazer/registrar/adiar) | `mocks_service.status()` |
| **Registrar estudo** (formulário completo: data, disciplina, assunto, tipo, minutos, questões, revisão, avançar ciclo) | `disciplines()`, `SESSION_TYPES`; pré-preenchido com os dados do bloco atual |
| **Revisões de hoje** (até 6, com urgência, método, nº de revisões já feitas, botão concluir) | `reviews_service.due(limit=6)` |
| Badge "N na fila" | `reviews_service.counts()` (`due`, `late`, `week`, `total`) |
| **Hoje**: minutos PRF | `stats.today_summary().prf_minutes` — `SUM(actual_minutes) WHERE date = hoje` |
| **Hoje**: questões `X / meta` + % acerto | `today_summary` + `settings.questions_goal_per_folga` (50) |
| **Hoje**: revisões | `review_counts.due` |
| **Hoje**: minutos de faculdade | `SUM(college_sessions.minutes) WHERE date = hoje` |
| **Hoje**: estado do simulado | `mock_status.state` |
| **Hoje**: treino | `today_summary.workout` (sessão TAF do dia) ou `active_workouts` (planos vigentes) |
| **Ciclo**: blocos feitos/total + barra, minutos vs meta, questões vs meta | `cycle_service.progress()` |
| **Desempenho (30 dias)**: média de acerto + delta vs 30 dias anteriores; horas, questões, nº simulados | `stats.overall(days=30)` + `stats.evolution(days=30)` |
| **Atenção**: 3 disciplinas fracas | `stats.weak_disciplines(days=90, limit=3)` — acurácia < 70% com ≥10 questões |
| **Atenção**: 4 assuntos fracos | `stats.weak_points(days=90, limit=4)` — mesma regra, por assunto |
| **Pendências fora do ciclo**: treino iniciado e não encerrado | `workouts_service.open_session()` |
| **Pendências fora do ciclo**: até 4 tarefas de faculdade vencendo em ≤14 dias | query inline em `dashboard.py:31-34` |
| **Sequência do ciclo**: próximos 4 blocos | `cycle_service.upcoming(limit=4)` |

Contexto global injetado em toda página (`app/__init__.py:73-92`): `today`, `app_version`,
`nav_active`, `review_badge`, `demo_active`, `auth_enabled`.

---

## 14. AUTOMAÇÕES

O sistema é deliberadamente pobre em automações. **Não existe cron, scheduler, thread de fundo,
webhook, nem qualquer processo que rode sem uma requisição HTTP do usuário.**

| # | Automação | Disparo | O que faz | Dados que altera | Desativável? |
|---|---|---|---|---|---|
| 1 | **Migrations automáticas** | Todo `create_app()` (todo start) | Aplica `.sql` pendentes em ordem | Schema + `schema_migrations` | Sim, via `SKIP_AUTO_MIGRATE` (usado só em testes) |
| 2 | **`ensure_base_data`** | Todo start | Insere `DEFAULTS` faltantes em `settings`; se `disciplines` está vazia, insere as **14 hardcoded**; se `taf_tests` está vazia, insere os 4; **se não há nenhum ciclo, cria o Ciclo #01 completo com todos os blocos** | `settings`, `disciplines`, `taf_tests`, `study_cycles`, `cycle_blocks` | **Não** (mesma flag do item 1) |
| 3 | **Percentual de questões** | Salvar questões (sessão ou avulso) | `percentage(correct,total)`; `wrong = total - correct`; clampa `correct ≤ total` | `questions.percentage/wrong` | Não |
| 4 | **Questões junto da sessão** | `POST /sessoes/salvar` com `questions_total > 0` | Cria **ou atualiza** a linha de `questions` ligada à sessão; deriva `kind` do tipo da sessão | `questions` | Sim — basta deixar o campo vazio |
| 5 | **Revisão junto da sessão** | Checkbox `create_review` | `create_review()` com origem = data da sessão | `reviews` | Sim (checkbox) |
| 6 | **Avanço do ciclo junto da sessão** | Checkbox `advance_cycle` | `advance()`: marca bloco como feito + `position += 1` | `cycle_blocks.done/done_at`, `study_cycles.current_position` | Sim (checkbox) |
| 7 | **Reagendamento da revisão** | `POST /revisoes/<id>/concluir` | Calcula `next_date` (passo + fator de dificuldade), `times_done += 1`, mantém `status='pendente'` | `reviews` | **Não** — concluir sempre reagenda |
| 8 | **Sessão a partir da revisão** | Checkbox `register_session` + minutos > 0 na conclusão | Insere `study_session` tipo `revisao` | `study_sessions` | Sim (checkbox) |
| 9 | **Encerramento do ciclo anterior** | `create_cycle()` (montar novo ciclo) | `close_cycle()` no ativo antes de criar o novo | `study_cycles.status` | Sim (parâmetro `close_active`, **não exposto na UI**) |
| 10 | **Reset de posição ao regerar** | `rebuild_blocks()` | `DELETE` de todos os blocos + `current_position = 1` | `cycle_blocks`, `study_cycles` | **Não** — é o comportamento do botão (avisado no flash) |
| 11 | **`clear_snooze` ao registrar simulado** | Criar um `mock_exam` novo | Limpa `mock_snooze_until` | `settings` | Não |
| 12 | **Recálculo do total do simulado** | Checkbox `recalc_total` | Soma `mock_exam_results` e sobrescreve totais do simulado | `mock_exams` | Sim (checkbox) |
| 13 | **`current_mark` do TAF** | Nova medição | Copia a medição mais recente para `taf_tests` | `taf_tests.current_mark/measured_at` | Não |
| 14 | **Cópia da prescrição** | Iniciar treino | Copia exercícios do plano para `taf_session_exercises` | novas linhas | Não |
| 15 | **Duração e "pulado"** | Encerrar treino | Calcula minutos por `started_at`; exercícios `pendente` → `pulado` | `taf_workout_sessions`, `taf_session_exercises` | Parcial (aceita minutos manuais) |
| 16 | **Erro → `revisado`** | `POST /erros/<id>/revisar` | Cria revisão e muda o status do erro | `mistakes.status`, `reviews` | Não (é a própria ação) |
| 17 | **Criação de assunto ao digitar** | Qualquer form com `subject_name` | Busca case-insensitive; se não existe, cria com `status='em_andamento'` | `subjects` | Não |
| 18 | **Desativar em vez de excluir** | Excluir disciplina com histórico | `active = 0` no lugar do DELETE | `disciplines.active` | Não |
| 19 | **Backup de segurança antes do restore** | `POST /dados/backup/restaurar` | Copia o banco atual para `prf-antes-restore-<timestamp>.db` | arquivo | Não |
| 20 | **Bloqueio por tentativas de login** | 5 falhas | Bloqueia o IP por 15 min (contador **em memória**, zera no restart) | memória do processo | Não |

**Automação que NÃO existe** (e é decisão explícita de projeto): nada cria revisão sozinho, nada
cria simulado sozinho, nada altera `target_minutes` sozinho, nada avança o ciclo pelo relógio,
nada encerra o ciclo pela data, nada envia notificação.

---

## 15. REGRAS DE NEGÓCIO (extraídas do código)

### Ciclo
1. Existe no máximo **um** ciclo `ativo`; criar/reabrir um encerra os demais (`cycle.py:96-101, 240-243`).
2. `current_position` só muda por ação explícita; **nunca** por data (`cycle.py:192-210`).
3. `new_position = min(position + 1, total_blocks + 1)` — não passa do fim.
4. `set_position` clampa em `[1, total+1]`.
5. Regerar blocos **apaga todos os blocos e zera a posição para 1** (`rebuild_blocks`).
6. `end_date = start_date + days - 1`; `days` default = `cycle_days` (14).
7. `goal_minutes`/`goal_questions` são **copiados** de settings para o ciclo na criação (o ciclo
   fica congelado se as settings mudarem depois).
8. `progress()` conta minutos/questões pelo **intervalo de datas do ciclo** — inconsistente com a
   regra 2.
9. Não há validação entre o total planejado (1875 min) e `goal_minutes` (1800) ou
   `estimated_capacity()`.
10. Não há regra que impeça blocos consecutivos da mesma disciplina quando ela tem > 50% dos
    blocos (`_separate_neighbours` desiste graciosamente).

### Disciplinas / pesos / prioridade
11. `target_minutes == 0` → disciplina **fora do ciclo**.
12. `active == 0` → fora do ciclo e fora de `stats.by_discipline` (`WHERE d.active = 1`).
13. `count = max(1, round(target/block))` → **toda disciplina com `target > 0` tem no mínimo 1
    bloco**, mesmo com meta de 5 minutos.
14. `block_minutes` mínimo forçado a 5 nos formulários.
15. `incidence` é usado como **desempate de ordem** e como parâmetro nas sugestões — nunca para
    dimensionar tempo.
16. `priority` **não tem efeito algum** exceto na regra 24.
17. `status` da disciplina não afeta o ciclo; afeta apenas as sugestões (regras 22-23).
18. `disciplines.position` é gravado por `POST /disciplinas/ordenar` mas a listagem ordena por
    `incidence DESC, name` — a ordenação manual **não tem efeito visível**.
19. Excluir disciplina com sessões → desativa em vez de apagar.

### Questões
20. `correct` é clampado em `[0, total]`; `total <= 0` rejeita o registro.
21. `kind = 'revisao'` se a sessão for do tipo `revisao`, senão `novo`.
22. `percentage` gravado com 2 casas; agregações recalculam do zero.

### Sugestões de ajuste (`adaptive.py`) — **nunca aplicadas sozinhas**
23. Disciplina `nao_iniciada` → sempre `manter` (mesmo com 0 questões e 0 minutos).
24. `< 10` questões no período → amostra insuficiente; o simulado assume o papel de sinal
    principal, se houver ≥ 5 questões nele.
25. `accuracy < performance_low` (60) → `aumentar`.
26. `performance_low ≤ accuracy < performance_mid` (60–70) → `manter`, exceto se
    `incidence ≥ 10` → `aumentar`.
27. `accuracy ≥ 85` **e** `incidence < 6` **e** `priority == 'complementar'` → `reduzir`
    (único uso de `priority` no sistema).
28. `mock_pct < 60` → força `aumentar`; `mock_pct < 70` cancela um `reduzir`.
29. `stale_days ≥ 14` (sem estudo) → força `aumentar`.
30. Passo de ajuste fixo: **±30 min** (`STEP_MINUTES`), com piso em 0.
31. Ordenação das sugestões: `aumentar` → `reduzir` → `manter`, e dentro de cada grupo por
    incidência desc.

### Revisões
32. Primeiro intervalo = `intervals()[0]` (1 dia), salvo `first_interval` informado.
33. `interval = max(1, round(intervals[step] * fator))`, fator ∈ {1.5, 1.0, 0.6}.
34. Após o último passo, o maior intervalo se repete para sempre.
35. Concluir **sempre** reagenda (`status` volta a `pendente`); a revisão só sai da fila por
    `arquivar` ou `excluir`.
36. Atraso não é penalizado: `next_date` é calculado a partir da **data de conclusão**.
37. `snooze` parte de `max(next_date, hoje)`.
38. Fila ordenada por `next_date`, depois `incidence DESC`.

### Simulados
39. `correct` clampado em `[0, total]`.
40. Frequência mapeada por dicionário fixo (7/14/30/None).
41. `snooze` só silencia o aviso; não altera frequência nem ciclo.
42. Registrar um simulado novo limpa o snooze.
43. `strong`/`weak` por `performance_mid` (70%).
44. Resultado por disciplina com `< 5` questões é ignorado pelas sugestões.

### TAF
45. Só **uma** sessão `em_andamento` por vez é reconhecida (`open_session` faz `LIMIT 1`), mas
    **nada impede** criar duas.
46. Iniciar treino sem exercícios cadastrados **falha silenciosamente** (`start_session` retorna
    `None`).
47. Encerrar marca exercícios `pendente` como `pulado`.
48. Apagar o plano preserva o histórico (`SET NULL` + `workout_name` copiado).
49. `delta` de evolução é invertido quando `higher_is_better = 0`.
50. Métricas do TAF **nunca** entram no cálculo do ciclo PRF.

### Faculdade
51. Semana começa na segunda-feira.
52. Minutos de faculdade **nunca** somam aos minutos PRF.
53. Tarefas com vencimento ≤ 14 dias aparecem como pendência informativa.

### Segurança / dados
54. App publicada **sem** senha configurada recusa servir para host não-local (HTTP 503).
55. `PRF_PASSWORD_HASH` definido + `SECRET_KEY` ainda igual ao de exemplo → **a app não sobe**.
56. Import/export só aceitam tabelas da whitelist; colunas validadas contra `PRAGMA table_info`;
    coluna `id` é descartada no import.

---

## 16. CONFIGURAÇÕES — valores atuais

Todas em `settings` (chave-valor TEXT). Valores lidos do banco real; defaults em
`services/settings.py:13-46`.

| Chave | Valor atual | Default | Editável na UI? | Efeito real |
|---|---|---|---|---|
| `cycle_days` | **14** | 14 | ✅ | duração nominal do ciclo; define `end_date` |
| `prf_goal_minutes` | **1800** | 1800 | ✅ | meta de minutos copiada para o ciclo. **Não limita o plano** |
| `questions_goal_per_cycle` | **350** | 350 | ✅ | meta de questões do ciclo |
| `questions_goal_per_folga` | **50** | 50 | ✅ | meta diária exibida no dashboard |
| `block_long` | **90** | 90 | ✅ | só rotula `block_size` |
| `block_medium` | **60** | 60 | ✅ | idem |
| `block_short` | **45** | 45 | ✅ | idem |
| `plantao_hours` | **2** | 2 | ✅ | só `estimated_capacity()` (informativo) |
| `folga_hours` | **6** | 6 | ✅ | idem |
| `plantoes_per_cycle` | **7** | 7 | ✅ | idem |
| `folgas_per_cycle` | **7** | 7 | ✅ | idem + divisor na tela de questões |
| `review_intervals` | **`1,7,15,30,60`** | idem | ✅ | intervalos da revisão espaçada |
| `review_difficulty_easy_factor` | **1.5** | 1.5 | ✅ | multiplicador "fácil" |
| `review_difficulty_hard_factor` | **0.6** | 0.6 | ✅ | multiplicador "difícil" |
| `mock_frequency` | **quinzenal** | quinzenal | ✅ | intervalo do aviso de simulado |
| `mock_default_minutes` | **300** | 300 | ✅ | pré-preenche cronômetro/formulário |
| `mock_default_questions` | **120** | 120 | ✅ | idem |
| `mock_snooze_until` | **`""`** (vazio) | `""` | ⚠️ indireta (botão adiar) | silencia o aviso até a data |
| `taf_minutes_per_cycle` | **420** | 420 | ✅ | meta informativa na tela TAF (janela de 14 dias fixos) |
| `college_hours_per_week` | **4** | 4 | ✅ | meta semanal de faculdade |
| `performance_low` | **60** | 60 | ✅ | limiar "ruim" (cores + sugestões) |
| `performance_mid` | **70** | 70 | ✅ | limiar "atenção" (cores + weak_points + strong/weak do simulado) |
| `questions_split_new` | **30** | 30 | ✅ | **apenas exibido** — nenhuma regra usa |
| `questions_split_review` | **20** | 20 | ✅ | **apenas exibido** — nenhuma regra usa |

**24 chaves.** Nenhuma configuração de ciclo/distribuição/peso além destas — ver seção 19 para o
que ficou hardcoded fora daqui.

---

## 17. ROTAS / API

**98 rotas registradas.** Não há API REST — é uma app HTML clássica (`GET` renderiza,
`POST` grava e redireciona). Único endpoint JSON: `/disciplinas/api/assuntos`.
Padrão recorrente: campo oculto `next` com uma URL relativa para retornar à tela de origem
(`common.redirect_target`).

### Painel e ciclo
| Método | Rota | Função |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/ciclo/` | Ciclo atual, blocos, progresso, histórico |
| GET/POST | `/ciclo/montar` | Monta plano do próximo ciclo (ou regera o atual) |
| POST | `/ciclo/avancar` | Conclui o bloco e avança a posição |
| POST | `/ciclo/posicao` | Ajuste manual da posição |
| POST | `/ciclo/bloco/<id>` | Editar / `toggle` concluído / `delete` do bloco |
| POST | `/ciclo/bloco/novo` | Adiciona bloco ao fim |
| GET | `/ciclo/<id>/relatorio` | Relatório de fechamento |
| POST | `/ciclo/<id>/encerrar` \| `/reabrir` | Muda status do ciclo |

### Disciplinas e assuntos
`GET /disciplinas/` · `POST /disciplinas/nova` · `GET /disciplinas/<id>` ·
`POST /disciplinas/<id>/salvar` · `POST /disciplinas/<id>/excluir` (desativa se houver histórico) ·
**`POST /disciplinas/pesos`** (edição em lote de incidência/meta/prioridade/status) ·
`POST /disciplinas/ordenar` (grava `position` — sem efeito prático) ·
`POST /disciplinas/<id>/assuntos` (aceita vários por linha) ·
`POST /disciplinas/assuntos/<id>/salvar` · `/excluir` ·
**`GET /disciplinas/api/assuntos?discipline_id=N` → JSON `{subjects:[{id,name}]}`**

### Sessões, questões, erros, revisões
`GET /sessoes/` (filtros: disciplina, tipo, período) · `GET /sessoes/nova?block_id=N` ·
**`POST /sessoes/salvar`** (a rota mais importante: grava sessão + questões + revisão + avanço) ·
`GET /sessoes/<id>/editar` · `POST /sessoes/<id>/excluir`
`GET /questoes/` (9 filtros) · `POST /questoes/salvar` · `GET /questoes/<id>` · `/excluir`
`GET /erros/` · `POST /erros/salvar` · `POST /erros/<id>/status` · **`POST /erros/<id>/revisar`** ·
`/excluir`
`GET /revisoes/` · `POST /revisoes/nova` · **`POST /revisoes/<id>/concluir`** ·
`/adiar` · `/salvar` · `/arquivar` · `/reativar` · `/excluir`

### Simulados, desempenho
`GET /simulados/` · `POST /simulados/salvar` · `GET /simulados/<id>` ·
`POST /simulados/<id>/resultado` (UPSERT por disciplina) · `POST /simulados/resultado/<id>/excluir` ·
`POST /simulados/<id>/erro` · `POST /simulados/adiar` · **`GET /simulados/cronometro`** ·
`POST /simulados/<id>/excluir`
`GET /desempenho/?days=N` · `GET /desempenho/ajustes?days=N` ·
**`POST /desempenho/ajustes/aplicar`** (única rota que altera `target_minutes` fora dos CRUDs)

### TAF e treinos
`GET /taf/` · `POST /taf/testes/salvar` · `POST /taf/testes/<id>/marca` · `/excluir` (desativa)
`GET /taf/treinos/` · `POST /taf/treinos/salvar` · `GET /taf/treinos/<id>` · `/excluir` ·
`GET|POST /taf/treinos/<id>/exercicios/{novo,salvar}` ·
`GET /taf/treinos/exercicios/<id>/editar` · `POST .../acao` (mover/duplicar/excluir) ·
**`POST /taf/treinos/<id>/iniciar`** · `GET /taf/treinos/execucao/<id>` (modo guiado) ·
`POST .../serie` · `POST .../serie/<id>/excluir` · `POST .../exercicio` (status) ·
`POST .../encerrar` · `GET .../resumo` · `POST .../excluir` · `GET /taf/treinos/historico`

### Faculdade, configurações, dados, auth
`GET /faculdade/` + CRUDs de disciplinas/tarefas/sessões
`GET /configuracoes/` · `POST /configuracoes/salvar` · `POST /configuracoes/demo` (seed/clear)
`GET /dados/` · `GET /dados/exportar/<table>.csv` · `GET /dados/exportar.json` ·
`POST /dados/importar` · `POST /dados/backup` · `GET /dados/backup/<name>` ·
`POST /dados/backup/restaurar`
`GET|POST /entrar` · `POST /sair` · **`GET /saude`** (healthcheck público, `{"ok": true}`)

---

## 18. COMPONENTES FRONTEND

Não há componentes JS — são **templates Jinja2**. O único arquivo de "componentes" é
`templates/partials/_macros.html` (71 linhas).

### Macros reutilizáveis (`_macros.html`)
`discipline_select()`, `subject_fields()` (select + campo de texto livre para criar na hora),
`progress_bar()`, `accuracy()` (badge colorido por limiar), `delta()` (variação com sinal).

### Telas

| Tela | Arquivo | Responsabilidade |
|---|---|---|
| Base | `base.html` | Layout, navegação com badge de revisões, flash messages, aviso de demo |
| **Painel** | `dashboard/index.html` (392) | Ver seção 13 |
| Ciclo | `cycles/index.html` (237) | Lista os blocos com posição, edição inline, toggle de concluído, ajuste manual da posição, histórico de ciclos |
| Montar ciclo | `cycles/build.html` (114) | Edita metas/blocos por disciplina + **preview da sequência antes de gerar**; opção "regerar o atual" |
| Relatório de ciclo | `cycles/report.html` (185) | Fechamento: minutos, questões, top disciplinas, simulados, revisões, treinos, faculdade, evolução, pontos fracos, 5 sugestões |
| Disciplinas | `disciplines/index.html` (83) | Tabela editável em lote (incidência, meta, prioridade, status) + totais |
| Disciplina | `disciplines/detail.html` (162) | Dados da disciplina, assuntos com acurácia/minutos/revisões pendentes, sessões recentes, erros abertos |
| Sessões | `sessions/index.html` (88) | Histórico filtrável + totais |
| Formulário de sessão | `sessions/form.html` (101) | **A tela mais importante**: um form grava sessão + questões + revisão + avanço do ciclo |
| Questões | `questions/index.html` (152) | Registro avulso, 9 filtros, totais, progresso vs meta do ciclo |
| Detalhe da questão | `questions/detail.html` (53) | Edição de um lote |
| Caderno de erros | `mistakes/index.html` (132) | Lista filtrável, distribuição por categoria, ações de status e "gerar revisão" |
| Revisões | `reviews/index.html` (208) | Hoje/atrasadas, próximas N dias, arquivadas, criação manual, edição de data/intervalo |
| Simulados | `mocks/index.html` (138) | Lista, gráfico SVG da evolução, aviso de frequência |
| Detalhe do simulado | `mocks/detail.html` (183) | Lançamento por disciplina, fortes/fracas, min/questão, delta vs anterior, erros do simulado |
| **Cronômetro** | `mocks/timer.html` (75) | Modo prova real, tela limpa, sem navegação. **Único componente que exige JS** |
| Desempenho | `performance/index.html` (136) | Geral, por disciplina, por assunto, evolução, série diária em SVG, erros por categoria |
| Sugestões | `performance/adjustments.html` (99) | Cada sugestão com direção, delta, **motivos textuais** e botão de aplicar individual |
| TAF | `taf/index.html` (180) | Testes, marcas, progresso vs meta, treinos vigentes, execuções recentes |
| Treinos | `workouts/{index,detail,exercise_form,run,session,history}.html` | Planos, prescrição, **execução guiada série a série**, resumo, histórico |
| Faculdade | `college/index.html` (178) | Disciplinas, tarefas, sessões, horas da semana vs meta |
| Configurações | `settings/index.html` (150) | Todas as 24 chaves + seed/limpeza de demo |
| Dados | `data/index.html` (78) | Export CSV/JSON, import CSV, backup/restore |
| Auth | `auth/{login,blocked}.html` | Login e telas de recusa (sem senha / CSRF) |

### JavaScript (`static/js/app.js`, 132 linhas, sem framework)
1. Confirmação em ações destrutivas (`data-confirm`);
2. Selects dependentes: ao trocar a disciplina, busca os assuntos em
   `/disciplinas/api/assuntos`. **Degrada bem**: se falhar, o campo de texto livre continua
   funcionando;
3. Cronômetro do simulado.

A app funciona **inteira sem JavaScript**, exceto o cronômetro.

---

## 19. PROBLEMAS E INCONSISTÊNCIAS

### 🔴 Críticos (afetam o resultado do estudo)

**P1 — Arredondamento do nº de blocos distorce as metas em ±33%.**
`count = max(1, int(target/block + 0.5))` (`cycle.py:74`) faz o tempo real divergir da meta:

| Disciplina | Meta | Real no ciclo | Erro |
|---|---|---|---|
| Espanhol | 90 | **120** | **+33%** |
| Ética | 90 | 120 | +33% |
| Penal / Proc. Penal | 90 | 120 | +33% |
| Leg. Especial | 105 | 120 | +14% |
| **Administrativo** | **120** | **90** | **−25%** |
| **Constitucional** | **120** | **90** | **−25%** |
| Dir. Humanos / Geopolítica / Física | 60 | 45 | −25% |

Resultado prático: **Espanhol (prioridade `base`, incidência 6,7%) recebe mais tempo de ciclo que
Direito Administrativo e Constitucional**, cujas metas declaradas são maiores. O sistema nunca
avisa da divergência.

**P2 — `priority` é campo morto.** `maxima|base|complementar` é editável em duas telas, ocupa
coluna no banco, aparece em relatórios, e **não influencia nada** na geração do ciclo. O único uso
funcional é a regra 27 do `adaptive` (permitir `reduzir` uma complementar). Um usuário que marcar
uma disciplina como `maxima` esperando mais tempo não terá efeito nenhum.

**P3 — `incidence` (o "peso") não dimensiona tempo.** Serve só como desempate de ordem. CTB com
25% e Física com 4% recebem tempo proporcional a `target_minutes`, que é digitado à mão. Não há
nenhuma função que converta peso em minutos.

**P4 — A ordem privilegia quem tem mais blocos, não quem é mais importante.** Chave `(i+0.5)/k`:
disciplinas com 2 blocos ficam em `0.25`/`0.75`; com 1 bloco, em `0.5`. Por isso **Espanhol
aparece na posição 3** enquanto **Administrativo só na 13 e Constitucional na 14** — as duas
disciplinas de `target` maior entre as `base`. Combinando P1+P4: o erro de arredondamento
promove a disciplina duas vezes (mais tempo **e** mais cedo).

**P5 — Nenhuma validação entre plano e meta/capacidade.** Plano atual: **1875 min**;
`prf_goal_minutes`: **1800**; `estimated_capacity()`: 7×2h + 7×6h = **3360 min**. Os três números
convivem sem nenhuma checagem, aviso ou normalização.

**P6 — `progress()` contradiz a regra central do ciclo.** O ciclo é calendário-independente por
projeto, mas minutos/questões do progresso são filtrados por
`date BETWEEN start_date AND end_date` (`cycle.py:263-272`). Um ciclo de 27 blocos que leve 20
dias perde 6 dias de registros no cálculo de progresso.

### 🟡 Lógica duplicada

**P7 —** A fórmula `max(1, int(target/block + 0.5))` existe em **dois lugares**:
`cycle.py:74` e `cycles.py:55`. Se um mudar, o preview e a geração divergem.

**P8 —** A geração de blocos existe em **duas implementações**: `cycle.rebuild_blocks()` (usa
`settings.block_size_name()`, lê do banco) e `seed._insert_blocks()` (usa um dict montado a partir
de `DEFAULTS`, **ignorando os valores gravados em `settings`**). Se o usuário mudar `block_medium`
para 50 e o banco for recriado, o seed rotula errado.

**P9 —** Limiares `performance_low`/`performance_mid` são lidos de settings em `stats.py`,
`adaptive.py`, `mocks.py` e `performance.py` — mas `utils.performance_level()` tem os defaults
`60`/`70` **hardcoded na assinatura** e o filtro Jinja `|level` é chamado **sem argumentos** em
todos os templates. Mudar os limiares em Configurações **não muda a cor dos badges**.

### 🟡 Valores hardcoded que deveriam ser configuráveis

| Valor | Local | O que controla |
|---|---|---|
| **As 14 disciplinas com incidência, prioridade, bloco e meta** | `seed.py:18-33` | todo o estado inicial |
| Os 4 testes de TAF e suas metas | `seed.py:35-40` | metas do TAF |
| `STEP_MINUTES = 30` | `adaptive.py:15` | passo de todo ajuste sugerido |
| `MIN_MOCK_QUESTIONS = 5` | `adaptive.py:18` | amostra mínima do simulado |
| `questions < 10` | `adaptive.py:50` | amostra mínima de questões |
| `accuracy >= 85`, `incidence < 6`, `incidence >= 10` | `adaptive.py:74,77` | gatilhos de aumentar/reduzir |
| `stale_days >= 14` | `adaptive.py:62,95` | "abandono" de disciplina |
| `min_questions=10`, `days=90` | `stats.py:100-117`, `dashboard.py:47-48` | o que entra em "Atenção" |
| `{semanal:7, quinzenal:14, mensal:30}` | `mocks.py:15` | frequência de simulado |
| `add_days(today, -13)` | `taf.py:56` | janela do TAF (ignora `cycle_days`) |
| `add_days(today, 14)` | `dashboard.py:34` | janela de tarefas de faculdade |
| `days=30` (evolução), `limit=6` (revisões), `limit=4` (blocos) | `dashboard.py` | conteúdo do painel |
| `[1,7,15,30,60]` fallback | `reviews.py:31` | intervalos (ok — há a setting) |
| `MAX_ATTEMPTS=5`, `BLOCK_MINUTES=15` | `auth.py:35-36` | brute-force |

### 🟡 Bugs aparentes

**P10 — `college.index` soma a semana sem limite superior:**
`WHERE date >= week_start` (`college.py:38`) — uma sessão lançada com data futura entra nas horas
da semana atual.

**P11 — `mocks.add_mistake` força `subject_id = NULL`** (`mocks.py:174`), mesmo que o formulário
pudesse informar o assunto. Erros vindos de simulado nunca entram em `stats.by_subject` (que faz
`JOIN subjects`).

**P12 — `sessions.save` no UPDATE não atualiza `cycle_id` nem `block_id`** (`sessions.py:116-121`).
Editar uma sessão pode deixar o vínculo com o ciclo desatualizado.

**P13 — `mistakes.needs_review` é gravado e nunca lido.** Nenhuma query no projeto filtra por ele.

**P14 — `reviews.status = 'concluida'`** existe no schema e nos comentários, mas **nunca é
gravado**. Concluir sempre volta para `pendente`.

**P15 — `disciplines.position` é gravado por `/disciplinas/ordenar` mas ignorado na listagem**
(`common.disciplines()` ordena por `incidence DESC, name`). Reordenação manual não tem efeito.
Só o seed inicial usa `position`.

**P16 — `start_session()` retorna `None` silenciosamente** quando o plano não tem exercícios
(`workouts.py:239-241`) — o usuário clica "iniciar" e nada acontece.

**P17 — `_separate_neighbours` pode não resolver todas as repetições** e não reporta.
No ciclo atual não há repetição vizinha, mas com uma disciplina dominante haveria — sem aviso.

**P18 — Bloqueio de login em memória** (`auth.py:38`): zera a cada restart e não funciona com
múltiplos workers. Assumido explicitamente na docstring, mas é uma limitação real em produção.

### 🟡 Funcionalidades parcialmente implementadas

- **`questions_split_new` / `questions_split_review`** (30/20): configuráveis, exibidos, e
  **nenhuma regra os usa**. Não há validação nem sugestão baseada no split.
- **`estimated_capacity()`**: calculado e exibido, mas nunca comparado ao plano.
- **`cycle_blocks.subject_id`**: existe, é editável bloco a bloco, mas a geração automática
  **sempre grava NULL**. Não há mecanismo que sugira o próximo assunto de uma disciplina.
- **`cycle_blocks.focus`**: campo livre, editável, sem nenhuma leitura analítica.
- **`study_cycles.notes` / `disciplines.notes`**: gravados, pouco explorados.
- **Google Calendar**: adiado com justificativa (`ROADMAP.md`).
- **FSRS/SM-2**: recusado com justificativa.

### 🟢 Dependências desnecessárias
**Nenhuma.** `requirements.txt` tem 3 linhas, todas justificadas (`tzdata` é necessária no
Windows). Não há CDN, não há build step, não há `node_modules`. Este é um ponto forte do projeto.

### 🟢 Inconsistências frontend ↔ backend
Poucas, porque o frontend é renderizado pelo backend:
- O filtro `|level` ignora os limiares configurados (P9);
- `templates/cycles/build.html` mostra o preview via `plan_from_disciplines` + `spread`, mas o
  POST recalcula o `count` com sua **própria cópia** da fórmula (P7) — hoje idênticas, frágeis
  amanhã;
- O `<select>` de assuntos depende de JS; sem JS o usuário digita o nome e o backend resolve
  (degradação correta).

---

## 20. DISCIPLINAS — análise dedicada

### 20.1 Quais estão cadastradas
**14**, todas vindas de `seed.py:18-33` (**hardcoded**), inseridas apenas se a tabela estiver
vazia. Ver a tabela completa na seção 6.

### 20.2 Quais estão ativas
**Todas as 14** (`active = 1`). Nenhuma foi desativada.

### 20.3 Quais estão no ciclo
**Todas as 14**, com 27 blocos no total. O critério real de entrada é apenas
`active = 1 AND target_minutes > 0` — e as 14 satisfazem ambos.

### 20.4 Como a prioridade é definida
Existem **três campos que parecem prioridade** e apenas um funciona:

| Campo | Papel aparente | Papel real |
|---|---|---|
| `priority` (`maxima/base/complementar`) | prioridade declarada | **nenhum efeito no ciclo**; só a regra 27 do adaptive |
| `incidence` (%) | peso do edital | **só desempate de ordem** e insumo textual das sugestões |
| **`target_minutes`** | meta de minutos | **é a prioridade de verdade** — determina quantos blocos |

O `target_minutes` é definido de três formas: (a) valor hardcoded no seed; (b) edição manual em
`/disciplinas/` ou `/ciclo/montar`; (c) aplicação individual de uma sugestão do adaptive.

### 20.5 Como o sistema decide quais disciplinas estudar
```
1. SELECT * FROM disciplines WHERE active = 1  ORDER BY incidence DESC, name
2. descarta as que têm target_minutes = 0
3. count = max(1, round(target_minutes / block_minutes))
4. spread(): chave (i+0.5)/count → ordena por (chave, -count, ordem_de_entrada)
5. _separate_neighbours(): desfaz repetições vizinhas
6. INSERT dos blocos com position 1..N
7. current_position = 1 → o bloco 1 é o "próximo bloco"
```
Não há sorteio, não há adaptação em tempo real, não há reordenação por desempenho.
**Um ciclo gerado é uma lista estática até que o usuário mande regerar.**

### 20.6 ⚠️ Existe regra dando prioridade indevida ao Espanhol?

**Sim — e é um efeito colateral, não uma regra intencional.** Não há nenhuma linha no código que
mencione Espanhol. O problema é a combinação de três mecânicas:

1. **Arredondamento (P1).** Espanhol: `target = 90`, `block = 60` → `int(90/60 + 0.5) = int(2.0) = 2`
   blocos → **120 minutos reais contra 90 de meta (+33%)**.
   Ao mesmo tempo, Administrativo: `120/90 = 1.33 → 1` bloco → **90 minutos contra 120 de meta
   (−25%)**. O ciclo inverte a relação entre as duas: **Espanhol acaba com mais tempo que
   Administrativo e que Constitucional.**

2. **Chave de espalhamento (P4).** Com 2 blocos, as chaves são `0.25` e `0.75`. Todas as
   disciplinas de 1 bloco têm chave `0.5`. Logo, **todas as de 2 blocos aparecem antes de todas as
   de 1 bloco.**

3. **Desempate por incidência.** Sete disciplinas empatam com 2 blocos e chave `0.25`. O desempate
   é a ordem de entrada, que vem de `ORDER BY incidence DESC`. Espanhol tem **6,7%** — a maior
   incidência do grupo de 2 blocos (acima de Informática 5,8%, RLM 5,0%, Ética 5,0% etc.).
   **Espanhol vence o desempate e ocupa a posição 3.**

**Resultado observado no banco:** Espanhol é a **3ª disciplina do ciclo**, à frente de Direito
Administrativo (posição 13), Direito Constitucional (14), Direitos Humanos (15) e todas as
complementares — apesar de estar marcada como `nao_iniciada`, `priority = base` e ter a **menor
meta declarada** entre as `base`.

Agravante: por estar `nao_iniciada`, o `adaptive` **nunca sugere reduzir** o Espanhol
(regra 23: `status == 'nao_iniciada'` → sempre `manter`). O sistema não tem, hoje, nenhum caminho
automático de correção.

---

## 21. EXEMPLO PRÁTICO — usuário que acabou de começar um ciclo

Cenário real: `Ciclo #01`, `current_position = 1`, 27 blocos, nenhum concluído.

### Primeiro bloco
```
Posição 1 de 27
Legislação de Trânsito (CTB)
90 minutos (longo)
Assunto: — (NULL; a geração automática nunca preenche)
[Concluir bloco]  [Ver ciclo]
```
Dashboard mostra este bloco e pré-preenche o formulário "Registrar estudo" com a disciplina CTB e
90 minutos de placeholder.

### Segundo bloco
```
Posição 2 de 27 — Língua Portuguesa — 90 min (longo)
```

### Terceiro bloco
```
Posição 3 de 27 — Espanhol — 60 min (médio)      ← ver seção 20.6
```
A "Sequência do ciclo" no painel já mostra: `1 CTB (90) · 2 Português (90) · 3 Espanhol (60) ·
4 Informática (60)`.

### Como uma sessão é registrada
O usuário estuda CTB e preenche o card "Registrar estudo" no painel:

| Campo | Valor |
|---|---|
| Data | 2026-08-17 |
| Disciplina | Legislação de Trânsito (pré-selecionada pelo bloco) |
| Assunto | digita "Infrações" → **criado na hora** em `subjects` (`status='em_andamento'`) |
| Tipo | Questões |
| Tempo realizado | 85 |
| Questões / Acertos | 30 / 22 |
| ☑ Agendar revisão | método: Questões |
| ☑ Avançar ciclo | |

Um único `POST /sessoes/salvar` produz **quatro** efeitos:
```sql
INSERT INTO subjects       (discipline_id=1, name='Infrações', status='em_andamento')
INSERT INTO study_sessions (date, discipline_id=1, subject_id, type='questoes',
                            planned_minutes=90, actual_minutes=85, cycle_id=1, block_id=1)
INSERT INTO questions      (date, discipline_id=1, subject_id, total=30, correct=22, wrong=8,
                            percentage=73.33, kind='novo', session_id=<id>)
INSERT INTO reviews        (discipline_id=1, subject_id, title='Infrações',
                            origin_date='2026-08-17', next_date='2026-08-18',
                            step=0, interval_days=1, status='pendente', method='questoes')
UPDATE cycle_blocks  SET done=1, done_at='2026-08-17' WHERE id=1
UPDATE study_cycles  SET current_position=2 WHERE id=1
```
Flash: *"Sessão registrada: 85 min. 30 questões (73% de acerto). Revisão agendada. Ciclo avançou
para o próximo bloco."*

### Como o ciclo avança
`current_position: 1 → 2`. O painel passa a mostrar **Língua Portuguesa, 90 min, posição 2 de 27**.
Se o usuário não estudar por 5 dias, ao voltar o painel mostra **exatamente o mesmo bloco 2** —
nenhuma pendência, nenhum atraso, nenhum recálculo.
Se o usuário quiser pular sem marcar como feito: `POST /ciclo/avancar` com `mark_done=0` (o bloco
fica `done=0` e a posição avança mesmo assim).

### Como uma revisão é criada e reaparece
Criada acima com `next_date = 2026-08-18` (origem + `intervals[0]` = 1 dia).
No dia 18 ela aparece no card "Revisões de hoje" com urgência `hoje`.
Ao concluir marcando dificuldade **Difícil**:
```
next_step = 1 → base = intervals[1] = 7 dias
factor    = review_difficulty_hard_factor = 0.6
interval  = max(1, round(7 × 0.6)) = 4
next_date = 2026-08-18 + 4 = 2026-08-22
step=1, interval_days=4, times_done=1, last_done_at='2026-08-18', status='pendente'
```
Se marcasse **Fácil**: `round(7 × 1.5) = 11` → `2026-08-29`.
Se marcasse **Média**: `7` → `2026-08-25`.
Se concluísse só no dia 25 (7 dias atrasada), a próxima seria calculada a partir de **25**, sem
penalidade nenhuma.

### Como questões entram no sistema
Dois caminhos, mesma tabela:
- **Junto da sessão** (acima): uma linha em `questions` com `session_id` preenchido. Se o usuário
  editar a sessão depois, essa linha é **atualizada**, não duplicada.
- **Avulsas** em `/questoes/` (`POST /questoes/salvar`): mesma estrutura, `session_id = NULL`,
  com escolha manual de `kind` (`novo`/`revisao`), banca e fonte.

Efeito imediato: a acurácia de CTB nos últimos 30 dias passa a incluir 22/30 = 73,33%; o card
"Hoje" mostra `30 / 50` questões; `cycle.progress().questions_pct` sobe.

### Como um erro é registrado
Em `/erros/`:
```
Data:        2026-08-17
Disciplina:  Legislação de Trânsito
Assunto:     Infrações
Questão:     "Multa x medida administrativa em infração de trânsito"
Categoria:   C — Não conhecia o conteúdo
Explicação:  "Medida administrativa não é penalidade."
Status:      aberto
```
→ `INSERT INTO mistakes (...)`, `needs_review = 1` (gravado, nunca lido).

Aparece imediatamente na listagem do caderno, no gráfico "erros por categoria" de `/desempenho/`
e na aba de erros da disciplina. **Não altera o ciclo, não cria revisão, não muda
`target_minutes`.**

Se o usuário clicar em **"Gerar revisão"**:
```sql
INSERT INTO reviews (discipline_id=1, subject_id, title='Multa x medida administrativa...',
                     method='caderno_erros', notes='Medida administrativa não é penalidade.',
                     origin_date=hoje, next_date=hoje+1, step=0, status='pendente')
UPDATE mistakes SET status='revisado' WHERE id=<id>
```

---

## 22. CONCLUSÃO

### A) O que está funcionando corretamente

1. **A arquitetura.** Separação limpa `blueprints` (HTTP) / `services` (regra) / `db` (SQL). SQL
   visível, sem ORM, migrations versionadas e idempotentes. Fácil de auditar e de mudar.
2. **A filosofia do ciclo.** Posição independente de calendário é a decisão mais acertada do
   projeto: perder um dia não gera dívida, não reinicia nada, não pune. Está implementada de forma
   consistente em `advance()`/`next_block()`.
3. **"Sugerir, nunca aplicar".** O `adaptive` produz sugestões **com justificativa textual** e
   exige clique individual. O usuário entende de onde veio cada número.
4. **O formulário único de sessão.** Uma submissão grava sessão + questões + revisão + avanço.
   É o fluxo diário do sistema e está bem resolvido.
5. **Revisão espaçada previsível.** Simples, auditável, com toda data sobrescrevível pelo usuário.
   Recusar FSRS foi uma escolha coerente com o resto.
6. **TAF estruturado (migration 002).** A separação prescrição × execução com **cópia** no início
   da sessão é modelagem correta: editar o plano não reescreve o histórico.
7. **Isolamento de TAF e faculdade.** Não contaminam o ciclo PRF. Aparecem só como informação.
8. **Zero dependências supérfluas.** 3 pacotes. Sem build step, sem CDN, sem framework de front.
   A app funciona sem JS.
9. **Segurança para uso pessoal publicado.** Recusa subir com chave de exemplo; recusa servir sem
   senha para host externo; timezone independente do relógio do servidor (bug real evitado);
   backup automático antes de restore; whitelist no import/export.
10. **Documentação honesta.** `ROADMAP.md` lista o que **não** será feito e **por quê**.

### B) O que está incompleto

1. **`questions_split_new` / `questions_split_review`** (30/20): configuráveis, exibidos, sem
   nenhuma regra que os use.
2. **`cycle_blocks.subject_id`**: o bloco pode ter assunto, mas a geração automática sempre grava
   NULL e nada sugere o próximo assunto de uma disciplina.
3. **`estimated_capacity()`**: calculado, exibido, nunca comparado ao plano.
4. **`mistakes.needs_review`**: campo morto.
5. **`reviews.status = 'concluida'`**: valor previsto no schema, nunca gravado.
6. **`disciplines.position` + `/disciplinas/ordenar`**: rota funcional cujo resultado é ignorado
   pela listagem (P15).
7. **Erros de simulado não chegam ao assunto** (`subject_id` forçado a NULL — P11), então nunca
   entram na análise por assunto.
8. **Nenhum uso analítico do caderno de erros.** As 6 categorias existem e são contadas, mas não
   alimentam nenhuma decisão.

### C) O que está rígido demais

1. **As 14 disciplinas estão no código** (`seed.py`), não em dados. Mudança de edital exige editar
   Python (ou editar 14 registros à mão na UI).
2. **`priority` e `incidence` não fazem nada no ciclo.** O usuário tem três campos que parecem
   prioridade e só `target_minutes` funciona — e é o menos evidente dos três.
3. **`STEP_MINUTES = 30` fixo.** Todo ajuste sugerido é ±30 min, independentemente do tamanho da
   disciplina. Para Física (60 min) é 50%; para CTB (450) é 6,7%.
4. **Limiares de amostra fixos** (`questions < 10`, `min_questions = 10`, `stale_days >= 14`,
   `accuracy >= 85`, `incidence < 6`, `incidence >= 10`, `MIN_MOCK_QUESTIONS = 5`).
5. **Janelas de tempo hardcoded:** TAF usa 14 dias fixos ignorando `cycle_days`; faculdade usa 14
   dias; dashboard usa 30 e 90 dias.
6. **`{semanal:7, quinzenal:14, mensal:30}`** — não dá para configurar "a cada 10 dias".
7. **`|level` ignora os limiares configurados** (P9): mudar `performance_low`/`mid` em
   Configurações não muda as cores da interface.
8. **Regerar blocos zera a posição para 1** sem alternativa de preservar o progresso.

### D) O que está automatizado demais

Muito pouco — o sistema erra por automatizar **de menos**, não de mais. As exceções reais:

1. **`ensure_base_data` cria um ciclo completo no primeiro start**, com blocos gerados a partir de
   metas que o usuário nunca viu nem aprovou. É a origem do problema do Espanhol: **o ciclo atual
   nunca foi montado por decisão do usuário** — foi gerado pelo seed.
2. **Concluir uma revisão sempre reagenda.** Não há como dizer "isso está consolidado, encerre"
   sem usar `arquivar` (que a UI apresenta como ação diferente).
3. **`current_mark` do TAF sobrescreve sozinho** a partir da medição de data mais recente
   (comportamento razoável, mas silencioso).
4. **Encerrar treino marca exercícios como `pulado`** automaticamente — pode mascarar um treino
   encerrado por engano.

### E) O que deveria ser configurável

| Deveria ser configurável | Hoje está em |
|---|---|
| **Como o peso vira tempo** (fator peso→minutos, ou tempo total distribuído por incidência) | inexistente — só `target_minutes` manual |
| **O que `priority` significa** (multiplicador por nível, ou posição garantida) | inexistente |
| **Política de arredondamento de blocos** (para baixo / para cima / permitir bloco parcial) | `cycle.py:74` fixo |
| **Critério de ordenação do ciclo** (por peso / por prioridade / intercalado) | `spread()` fixo |
| **Passo de ajuste do adaptive** (absoluto ou % da meta) | `STEP_MINUTES = 30` |
| Limiares de amostra mínima (questões, simulado, dias sem estudar) | `adaptive.py`, `stats.py` |
| Gatilhos de aumentar/reduzir (85%, incidência 6/10) | `adaptive.py:74,77` |
| Janela de análise do dashboard (30/90 dias) | `dashboard.py` |
| Janela do TAF e da faculdade | `taf.py:56`, `dashboard.py:34` |
| Intervalo de simulado em dias livres | `mocks.py:15` |
| Lista de disciplinas como dado (import de edital) | `seed.py` |
| Tolerância entre plano e meta (avisar acima de X%) | inexistente |

### F) Principais pontos a alterar para o sistema seguir a metodologia

Ordenados por impacto sobre a qualidade do estudo:

**1. Corrigir a distorção do arredondamento (P1) — maior impacto imediato.**
Hoje o tempo real de uma disciplina difere da meta em até ±33%, e a distorção inverte a ordem de
importância entre Espanhol e Administrativo/Constitucional. Três caminhos possíveis:
(a) permitir bloco de tamanho variável para absorver o resto (`120/90 → 1×90 + 1×30`);
(b) arredondar para baixo com um bloco extra só se o resto ≥ 50% do bloco;
(c) redistribuir o total de minutos entre os blocos após o `spread`.
Em qualquer caso, **exibir o desvio meta × real na tela de montar ciclo**.

**2. Fazer `priority` e `incidence` realmente governarem o ciclo (P2, P3).**
Hoje `target_minutes` é a única prioridade real, e é preenchida à mão. A metodologia pede que o
peso do edital dirija o tempo. Sugestão: derivar `target_minutes` de
`incidence × tempo_total_do_ciclo`, com um multiplicador por `priority` — mantendo a possibilidade
de override manual por disciplina.

**3. Trocar o critério de ordenação (P4).**
A chave `(i+0.5)/k` faz o número de blocos ditar a ordem. Isso deveria depender de peso/prioridade,
não da quantidade. Uma ordenação por prioridade com intercalação garantiria que CTB e Português
apareçam entre as primeiras posições e que uma `base` de baixa incidência não caia na posição 3.

**4. Alinhar plano, meta e capacidade (P5).**
`1875 ≠ 1800` e `estimated_capacity() = 3360` convivem sem nenhuma verificação. Adicionar uma
validação na montagem do ciclo — nem que seja só um aviso: *"o plano soma 31h15, sua meta é 30h e
sua capacidade declarada é 56h"*.

**5. Desacoplar `progress()` do calendário (P6).**
Contar minutos/questões pelo **período de execução real do ciclo** (do início até hoje, ou entre a
1ª e a última sessão vinculada ao `cycle_id`), não pela janela fixa de 14 dias — para que a
métrica pare de contradizer a regra central do sistema.

**6. Rever a regra "`nao_iniciada` → sempre manter" (regra 23).**
Espanhol, Informática, Direitos Humanos, Geopolítica e Física estão `nao_iniciada` **e ocupando
9 dos 27 blocos**. O adaptive não tem nada a dizer sobre elas, mesmo quando ficam meses sem
progresso. Deveria haver um sinal para "alocada mas nunca tocada".

**7. Tirar as 14 disciplinas do código.**
Mover para um arquivo de dados (JSON/CSV) importável, para que a mudança de edital não exija
editar Python.

**8. Unificar as lógicas duplicadas (P7, P8, P9).**
Fórmula do `count` em dois lugares; geração de blocos em duas implementações (uma delas ignorando
as settings gravadas); limiares lidos de settings no Python mas hardcoded no filtro Jinja.

**9. Fechar as pontas soltas.**
`questions_split_*` sem uso, `needs_review` morto, `position` das disciplinas ignorado,
`subject_id` do bloco sempre NULL, erros de simulado sem assunto (P11), `sessions.save` que não
atualiza `cycle_id`/`block_id` (P12), semana de faculdade sem limite superior (P10),
`start_session` que falha em silêncio (P16).
