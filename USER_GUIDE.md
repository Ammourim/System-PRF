# Guia de uso

## O dia a dia (deve levar segundos)

1. Abra o **Painel**.
2. Veja **PROXIMO BLOCO** - ele diz o que estudar e por quanto tempo.
3. Clique em **Iniciar** (rola a tela ate o formulario ja preenchido).
4. Estude.
5. Preencha **tempo realizado** e, se fez questoes, **quantidade e acertos**. Escreva a
   observacao se algo travou.
6. Marque **Concluir bloco e avancar o ciclo** e salve.
7. Olhe **Revisoes de hoje** e conclua o que der.

Pronto. Todo o resto do sistema existe para quando voce quiser olhar mais fundo.

### O que fazer quando o dia nao colabora

| Situacao | O que fazer |
| --- | --- |
| So sobraram 30 minutos | Registre 30. O bloco planejava 90? A diferenca aparece, nada quebra. |
| Plantao rendeu 2h em vez de 1h | Registre e conclua dois blocos. Nada limita. |
| Passei tres dias sem estudar | Nada. Volte e o proximo bloco e o mesmo de antes. |
| Estudei fora da ordem do ciclo | Registre normalmente e ajuste a posicao em **Ciclo -> Ajustar posicao**. |
| Nao quero este bloco agora | **Pular sem marcar** no Painel: avanca sem dar o bloco como feito. |

## Ciclo

O ciclo e uma lista de blocos, nao uma agenda. O dia da semana nao importa.

* **Ciclo** mostra os blocos, a posicao atual e meta x realizado. Da para editar
  disciplina, assunto, duracao e foco de qualquer bloco, remover e acrescentar.
* **Montar ciclo** e onde voce define quanto tempo cada disciplina recebe no ciclo. Meta
  `0` deixa a disciplina de fora. A previa mostra a sequencia antes de gerar.
  * **Criar novo ciclo** encerra o atual (o historico fica) e comeca do bloco 1.
  * **Regerar blocos do ciclo atual** mantem o ciclo, refaz a lista e volta a posicao para 1.
* Quando todos os blocos terminam, o Painel oferece o **relatorio do ciclo**.

O ciclo inicial (V1) tem 27 blocos e ~31h15, distribuidos conforme a incidencia historica:
CTB 7h, Portugues 4h30, Constitucional/Administrativo/RLM/Informatica 2h cada, e assim por
diante. Tudo editavel.

## Registrar estudo

Um unico formulario grava a sessao e, opcionalmente:

* as **questoes** daquela sessao (percentual calculado sozinho);
* uma **revisao** do assunto;
* o **avanco do ciclo**.

O campo de tempo aceita `45`, `1:30`, `1h30` ou `1,5h`. O assunto pode ser escolhido da
lista **ou digitado** - se nao existir, e criado na hora.

## Questoes

Registro avulso (sem sessao), filtros por disciplina, assunto, banca, periodo e percentual,
alem de "so com erros". A tela mostra questoes no filtro, media diaria, acerto e o
andamento da meta do ciclo.

A referencia sugerida e **30 questoes do assunto novo + 20 de revisao** por sessao, e
50 questoes por folga. Sao sugestoes: mude em **Configuracoes**.

## Caderno de erros

Classifique todo erro:

| Codigo | Significado | O que costuma resolver |
| --- | --- | --- |
| `C` | Nao conhecia o conteudo | Teoria + questoes do assunto |
| `E` | Esqueci | Revisao espacada |
| `I` | Interpretacao | Leitura mais lenta, grifar comando |
| `A` | Atencao | Checagem final, ritmo de prova |
| `D` | Duvida entre alternativas | Comparar alternativas, mais questoes |
| `CH` | Chute | Conteudo nao coberto |

O grafico por categoria mostra qual e o seu tipo de erro dominante - e ele que diz se o
problema e conteudo, memoria ou execucao. **Gerar revisao** transforma um erro em item da
fila com metodo "caderno de erros".

## Revisoes

Uma fila, nao um calendario. Ela mostra atrasadas e de hoje; o resto fica em "proximas".

Ao concluir, informe **dificuldade** e **metodo**. O proximo intervalo sai da lista
configurada (padrao `1, 7, 15, 30, 60` dias), ajustado pela dificuldade: facil alonga,
dificil encurta. Voce pode adiar (+1/+3 dias), editar a data na mao, arquivar como
consolidado e reativar depois.

Revisar nao e reler: registre o metodo real (questoes, flashcards, recuperacao ativa,
releitura, caderno de erros, mista).

## Simulados

* **Registrar simulado** com nota, tempo planejado e tempo gasto.
* Na tela do simulado, **lance o desempenho por disciplina** (a barra e a tabela mostram
  fortes e fracos) e registre os erros no caderno.
* Preencha a **estrategia de prova**: questoes que consumiram muito tempo, chutadas,
  deixadas para depois, tempo restante e sua percepcao. E o que faz o simulado valer mais
  que "quantas acertei".
* **Modo prova real**: cronometro em tela limpa, com tempo restante, decorrido, respondidas
  e restantes. Ao encerrar, ele preenche os tempos no formulario de registro.

### Quando fazer o proximo

O simulado **nao e um bloco do ciclo** - de proposito. E um evento grande (5h + correcao) que
raramente caberia no lugar onde o ciclo o colocasse, e travar isso brigaria com a escala 12x36.
Em vez disso o sistema **calcula e avisa**:

* o card **Proximo simulado** na tela de Simulados mostra sempre a data prevista e quantos
  dias faltam, a partir da frequencia configurada (padrao: quinzenal);
* a linha **Simulado** no card "Hoje" do Painel mostra o mesmo em uma linha;
* quando vence, aparece no Painel o aviso **Simulado recomendado**, com botoes para fazer
  agora (modo prova real), registrar um ja feito, ou **adiar 3 / 7 dias**.

Adiar silencia so o aviso - nao muda a frequencia configurada e nao mexe em nada do ciclo:
nenhum bloco e criado, adiado ou marcado. Registrar um simulado reinicia a contagem e limpa
o adiamento. Frequencia em **Manual** desliga o aviso por completo.

Se quiser que o tempo do simulado conte nas horas do ciclo, registre uma sessao do tipo
**Simulado** e outra de **Correcao de simulado** - assim realizacao e analise aparecem no
total de horas sem engessar o ciclo.

Nenhum simulado e criado automaticamente, em nenhuma hipotese.

## Desempenho

Visao geral por periodo (7 a 180 dias), volume diario, por disciplina com variacao versus
o periodo anterior, por assunto (ordenado do pior para o melhor) e erros por categoria.

**Sugestoes de ajuste** cruza incidencia, aproveitamento, tamanho da amostra, tempo sem
estudo, status da disciplina **e o desempenho no ultimo simulado**, e propoe aumentar /
manter / reduzir a meta de cada disciplina - **com o motivo escrito**. Voce clica em
**Aceitar** ou ignora. Aceitar muda apenas a meta; os blocos so mudam quando voce regerar
o ciclo.

O simulado pesa mais que a questao avulsa, porque foi feito sob pressao de tempo. Na pratica:

| Situacao | O que o sistema conclui |
| --- | --- |
| Vai bem nas questoes soltas, mal no simulado | Sugere **aumentar** - o problema e tempo/execucao, nao conteudo |
| Vai bem nos dois | Mantem (ou sugere reduzir, se a incidencia for baixa) |
| Ia reduzir, mas o simulado ficou na faixa de atencao | **Segura a reducao** - o simulado ainda nao confirmou |
| Poucas questoes no periodo, mas simulado ruim | Sugere **aumentar** usando o simulado como sinal |
| Disciplina marcada "nao iniciada" | Ignora o simulado - ir mal ali e esperado |

Resultados com menos de 5 questoes no simulado sao ignorados: amostra pequena demais.

## TAF

Cadastre os testes (corrida, barra, flexao, abdominal ou o que o edital trouxer) com
unidade e meta, marcando se **maior e melhor** (repeticoes) ou menor (tempo). Registre
marcas ao longo do tempo e acompanhe a evolucao percentual.

### Treinos: cadastro em duas etapas

O treino agora e uma estrutura, nao um registro unico:

```text
TREINO (plano)
  └── Exercicio 1, 2, 3...   (prescricao)
```

1. **Cadastre o treino** em TAF -> Treinos, com apenas os dados gerais: nome, objetivo,
   tipo, duracao prevista, vigencia e observacoes. Ao salvar, o sistema abre a pagina do
   treino.
2. **Adicione os exercicios** um a um. Cada um tem os seus proprios campos, e
   **nenhum e obrigatorio** - preencha so o que faz sentido:

| Exercicio | O que preencher |
| --- | --- |
| Barra fixa | Series 4 &middot; Repeticoes 6 &middot; Descanso 90s &middot; Meta "24 repeticoes" |
| Corrida | Series 1 &middot; Distancia 5 km &middot; Tempo total 30 min |
| Prancha | Series 4 &middot; Tempo por serie 45s &middot; Descanso 30s |

Na pagina do treino da para **reordenar** (setas), **duplicar** e **excluir** exercicios.
Campos de tempo aceitam `45` (segundos) ou `1:30` (= 90 segundos).

### Executar o treino

Na pagina do treino, **Iniciar treino**. A tela de execucao mostra um exercicio e uma
serie por vez, com botoes grandes para usar no celular durante o treino:

```text
Exercicio 1 de 4
BARRA FIXA
Serie 1 de 4
Meta da serie: 6 repeticoes
0 / 24 rep
[ Repeticoes ] [ Observacao ]
[   Concluir serie 1   ]
```

Ao completar as series previstas, o exercicio fecha e o proximo aparece sozinho. Da para
**pular exercicio** ou ir para o **proximo** a qualquer momento, e corrigir uma serie ja
registrada. So existe **um treino em andamento por vez** - se voce sair no meio, ele
aparece no painel como pendencia para retomar.

### Prescricao x realizado

Ao encerrar, o resumo mostra lado a lado o que estava previsto e o que voce fez:

```text
Barra fixa
Prescrito: 4 series x 6 rep - meta: 24 repeticoes
21/24 rep        Serie 1: 6 - Serie 2: 6 - Serie 3: 5 - Serie 4: 4
```

Cada execucao fica no **historico** (TAF -> Treinos -> Historico), o que permite acompanhar
a evolucao ao longo do tempo.

Excluir um exercicio ou um treino **nao apaga o historico**: as execucoes guardam uma copia
do que foi prescrito no dia.

O modulo organiza e acompanha treino. Nao e prescricao de treino nem orientacao medica.

## Faculdade

Modulo separado, fora do ciclo PRF: disciplinas, atividades com prazo (atividade,
trabalho, prova, leitura) e registro de horas contra a meta semanal (padrao 4h).
As atividades com prazo proximo aparecem no Painel.

## Configuracoes

Metas do ciclo, metas de questoes, tamanhos de bloco, disponibilidade da escala,
intervalos de revisao, frequencia e padroes do simulado, TAF, faculdade e limiares de
desempenho (que controlam as cores e as sugestoes). Nada disso esta fixo no codigo.

### Quando sair o edital

1. **Disciplinas**: ajuste incidencia, prioridade, status, meta e tamanho de bloco.
   Cadastre ou desative disciplinas.
2. Nas disciplinas, cadastre os **assuntos** do edital (a caixa aceita um por linha).
3. **Configuracoes**: ajuste duracao da prova e numero de questoes do simulado.
4. **TAF**: ajuste os testes e as metas conforme o edital.
5. **Montar ciclo**: gere o ciclo novo com os pesos novos.

## Backup

Em **Dados e backup**: gerar backup, baixar, restaurar, exportar CSV/JSON e importar CSV.
Faca um backup antes de importar qualquer coisa ou de mexer em muita configuracao.

## Dados de demonstracao

Se o sistema esta com dados de exemplo, aparece um aviso no topo e a etiqueta `demo` nos
registros. Remova em **Configuracoes -> Dados de demonstracao** quando quiser comecar
limpo - suas disciplinas, configuracoes e o ciclo continuam.
