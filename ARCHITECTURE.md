# Arquitetura

## Stack e por que

| Camada | Escolha | Motivo |
| --- | --- | --- |
| Linguagem | Python 3.11+ | Preferencia declarada; ja instalado na maquina. |
| Web | Flask | Framework minimo, estavel, sem convencoes escondidas. |
| Banco | SQLite (`sqlite3` da stdlib) | Arquivo unico, backup e copiar arquivo, zero servidor. |
| ORM | **nenhum** | O SQL fica visivel. Em uma aplicacao pessoal, um ORM adiciona uma camada de surpresa sem ganho real. |
| Front-end | Jinja2 + CSS/JS puro | Sem build, sem `node_modules`, sem versao para manter. A pagina funciona mesmo com JS desligado (exceto o cronometro). |
| Testes | pytest | Padrao. |

Dependencias totais em producao: **Flask**. Nada de microservicos, filas, Docker ou
segundo banco - isso e explicitamente contra o objetivo do projeto.

## Estrutura

```text
System-PRF/
├── run.py                    ponto de entrada
├── app/
│   ├── __init__.py           create_app(): config, migrations, filtros, blueprints
│   ├── config.py             variaveis de ambiente + parser .env proprio
│   ├── db.py                 conexao, helpers de query, migrations, backup/restore
│   ├── utils.py              parsing de formulario, datas, formatacao, percentuais
│   ├── seed.py               dados iniciais + dados de demonstracao
│   ├── migrations/           001_initial.sql, 002_*.sql ...
│   ├── services/             regras de negocio (o cerebro do sistema)
│   │   ├── settings.py       leitura/escrita das configuracoes
│   │   ├── today.py          objetivos do dia (o "ciclo" simplificado)
│   │   ├── subjects.py       assunto livre e conclusao do assunto
│   │   ├── cycle.py          ciclo detalhado (legado): blocos, posicao, progresso
│   │   ├── reviews.py        revisao espacada
│   │   ├── stats.py          desempenho, evolucao, pontos fracos
│   │   ├── adaptive.py       sugestoes de ajuste e relatorio de ciclo
│   │   └── dataio.py         export CSV/JSON e import CSV
│   ├── blueprints/           uma blueprint por area (rotas HTTP finas)
│   ├── templates/            Jinja2
│   └── static/               app.css e app.js (unicos arquivos)
├── tests/
├── scripts/preview_cycle.py
└── data/prf.db               criado na primeira execucao
```

**Regra de camadas:** blueprints leem o formulario, chamam um service e renderizam.
Calculo de verdade mora em `services/`. Isso e o que permite testar as regras sem HTTP -
`tests/test_cycle.py`, `test_reviews.py`, `test_today.py` e `test_stats.py` nao
passam por rota nenhuma.

## Conceito central: o sistema responde duas perguntas

    "O que eu preciso estudar hoje?"   -> objetivos do dia (services/today.py)
    "O que eu preciso revisar hoje?"   -> fila de revisoes (services/reviews.py)

Tudo o mais e secundario e vive fora da tela inicial. Detalhes da simplificacao:
`SIMPLIFICACAO.md`.

### Objetivos do dia (`services/today.py`)

Cada disciplina ativa tem uma **frequencia** (1 a 7 dias por semana; o padrao vem da
prioridade: maxima 5, alta 3, media 2, baixa 1). Um espalhamento tipo Bresenham garante
que, em quaisquer 7 dias consecutivos, a disciplina aparece exatamente `frequencia`
vezes - e o deslocamento por id evita que todas caiam no mesmo dia.

A funcao e pura em relacao ao banco: **abrir a tela nao grava nada** e a mesma data
sempre produz a mesma lista. Nao ha minutos, blocos, metas nem distribuicao matematica.
Um dia sem estudo nao gera pendencia: amanha o dia e recalculado do zero.

### Assunto e conclusao (`services/subjects.py`)

Registrar estudo **nunca** conclui um assunto. Estudar "Infracoes" tres dias seguidos
gera tres registros e o assunto continua em andamento. So quando o usuario declara
"terminei este assunto" o sistema grava `subjects.completed_at` e pergunta se deve
agendar as revisoes.

### Revisao espacada (`services/reviews.py`)

Sem algoritmo: proxima data = **data real da conclusao** + proximo intervalo da lista
(`review_intervals`, padrao 1,7,15,30,60). Atraso nao duplica linha; depois do ultimo
intervalo o assunto e consolidado e sai da fila.

## O ciclo antigo: preservado, fora do caminho

O ciclo com blocos, metas e distribuicao continua funcionando em
"Avancado > Ciclo detalhado". Nada foi removido - apenas saiu do fluxo diario.

## Conceito do ciclo detalhado: nao depende de calendario

Um ciclo e uma **lista ordenada de blocos** (`cycle_blocks`) e uma **posicao**
(`study_cycles.current_position`). O dashboard mostra o bloco da posicao atual. Concluir
um bloco faz `current_position += 1`. Sao essas as unicas coisas que mexem na posicao:

1. o usuario concluir um bloco;
2. o usuario pular um bloco explicitamente;
3. o usuario ajustar a posicao na mao.

Nenhum job, nenhuma data e nenhuma virada de dia mexe nisso. Por consequencia, ficar tres
dias sem estudar nao produz efeito algum: a posicao continua onde estava. E o que torna o
sistema compativel com a escala 12x36.

### Geracao dos blocos (`cycle.generate_cycle_plan`)

Tres campos com papeis separados, para que nenhum deles decida o que nao e da sua conta:

| Campo | Papel |
|---|---|
| `priority` (`maxima/alta/media/baixa`) | **a ORDEM** no ciclo |
| `target_minutes` | **o TEMPO** da disciplina no ciclo |
| `incidence` | desempate **dentro** da mesma prioridade |
| `desired_blocks` / `min_blocks` | controle manual: frequencia fixa e contato minimo |

**Quantidade e tamanho dos blocos** (`blocks_for_target`): nao existe `round()`. O sistema
usa o teto de `meta / bloco` - assim nenhum bloco fica maior que o tamanho preferido - e
distribui a meta entre esses blocos em multiplos de 5 minutos, somando **exatamente** a
meta. Antes, `round(120 / 90) = 1` transformava uma meta de 120 min em 90 min sem avisar;
hoje viram dois blocos de 60. Se o piso `cycle_min_block_minutes` for violado, cai para o
numero menor de blocos e a diferenca resultante e **mostrada na tela**, nunca escondida.

**Ordem** (`spread`): o ciclo e montado em rodadas. Numa rodada cada disciplina entra no
maximo uma vez, na ordem prioridade -> incidencia -> ordem recebida; uma disciplina com `k`
blocos entra na rodada `i * rodadas // k`, o que espalha os blocos sem furar a fila. Assim
uma disciplina de prioridade baixa **nunca** aparece cedo apenas por ter mais blocos.
`_separate_neighbours` desfaz repeticoes vizinhas, mas **somente dentro da mesma
prioridade** - de-clumping nunca custa a ordem.

**Meta do ciclo**: o total planejado e comparado com `prf_goal_minutes` dentro de
`cycle_goal_tolerance_pct`. Fora da tolerancia o sistema **avisa**; nao reescreve meta
nenhuma por conta propria.

O resultado e uma sugestao: a tela **Montar ciclo** mostra blocos, minutos reais e a
diferenca por disciplina antes de gerar, e a tela **Ciclo** permite editar, reordenar,
remover e acrescentar blocos manualmente.

## Revisao espacada: simples de proposito

Uma lista de intervalos configuravel (`review_intervals`, padrao `1,7,15,30,60`). Ao
concluir, o proximo intervalo da lista e multiplicado pelo fator da dificuldade informada
(`facil` alonga, `dificil` encurta, `media` mantem). Depois do ultimo intervalo, o maior se
repete.

Nao ha FSRS nem SM-2. A troca e consciente: o algoritmo sofisticado ganharia pouco aqui e
custaria previsibilidade - e o usuario precisa poder olhar uma data e entender de onde ela
veio. As revisoes vivem em uma **fila**, nunca em um calendario com centenas de eventos.

## Simulado: avisado, nao agendado

`services/mocks.py` calcula quando o proximo simulado vence (ultima data + intervalo da
frequencia configurada) e o painel avisa. O simulado **nao vira bloco do ciclo**: e um
evento de varias horas que raramente caberia na posicao onde o ciclo o colocasse, e
transformar isso em bloco produziria exatamente o atrito com a escala 12x36 que o projeto
quer evitar.

O aviso pode ser adiado (`mock_snooze_until`), o que silencia **apenas o aviso** - a
frequencia nao muda e nada do ciclo e tocado. Registrar um simulado limpa o adiamento e
reinicia a contagem. Frequencia `manual` desliga tudo. Ha teste garantindo que abrir a tela
nao cria simulado, sessao nem mexe na posicao do ciclo.

## Ciclo adaptativo: recomendar, nunca impor

`services/adaptive.py` cruza incidencia, prioridade, aproveitamento, tamanho da amostra,
tempo desde o ultimo estudo, status da disciplina e **o desempenho por disciplina no ultimo
simulado**, e produz uma sugestao `aumentar` / `manter` / `reduzir` **com os motivos
escritos**. O simulado entra como segundo sinal com peso maior que a questao avulsa (foi
feito sob pressao de tempo): ele pode reforcar a decisao, contradize-la ("vai bem nas
questoes soltas mas cai no simulado" -> aumentar) ou segurar uma reducao ainda nao
confirmada. Resultados com menos de `MIN_MOCK_QUESTIONS` questoes sao ignorados.

Duas garantias no codigo:

* `suggestions()` nao escreve nada no banco (ha teste para isso);
* aplicar um ajuste altera apenas a *meta* da disciplina. Os blocos do ciclo so mudam
  quando o usuario for a "Montar ciclo" e regerar.

## Decisoes de implementacao

* **Minutos, sempre.** Toda duracao no banco e um inteiro em minutos. A formatacao para
  `31h15` acontece no filtro Jinja `|minutes`. Nada de `float` de horas.
* **Entrada tolerante.** `parse_minutes` aceita `45`, `1:30`, `1h30` e `1,5h`. Campo vazio
  cai no padrao em vez de estourar erro - registrar precisa levar segundos.
* **Assunto criado ao digitar.** Em qualquer formulario da para escolher um assunto
  existente ou digitar um novo; ele e criado na hora (`common.resolve_subject`). Isso
  elimina o vai-e-volta de cadastrar antes de registrar.
* **`is_demo`.** Todo registro de demonstracao carrega essa flag, o que torna a limpeza
  exata e reversivel, sem tocar nos dados reais.
* **Migrations em `.sql` numerado.** Aplicadas em ordem, registradas em
  `schema_migrations`, executadas automaticamente no start. Nada de migracao implicita ou
  de `ALTER` escondido em codigo Python.
* **Meta x realizado nunca se misturam.** `planned_minutes` e `actual_minutes` sao colunas
  distintas e as duas aparecem na interface.

## O que foi deixado de fora e por que

* **Google Calendar.** Exige OAuth, `credentials.json`, tela de consentimento e um fluxo
  de refresh token - configuracao complexa demais para o ganho, e o proprio projeto define
  que a agenda nao pode ser requisito. Fica no ROADMAP.
* **Login/multiusuario.** Aplicacao local de uma pessoa so.
* **Gamificacao.** Por pedido explicito: o feedback e o desempenho real.
* **Notificacoes/jobs em segundo plano.** Qualquer processo automatico que mexesse em
  datas violaria o principio do ciclo.
