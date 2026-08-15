# Roadmap

## Concluido

### Fase 1 - MVP
- [x] Banco SQLite com migrations e indices
- [x] 14 disciplinas com incidencia, prioridade e status
- [x] Assuntos (cadastro em lote e criacao ao digitar no registro)
- [x] Ciclo de estudos com blocos intercalados e posicao independente de calendario
- [x] Registro de sessao em um formulario unico (tempo + questoes + revisao + avanco)
- [x] Modulo de questoes com filtros e percentual automatico
- [x] Caderno de erros com as 6 categorias
- [x] Dashboard: proximo bloco, hoje, ciclo, desempenho, atencao, pendencias

### Fase 2
- [x] Fila de revisao espacada com intervalos configuraveis
- [x] Metodo e dificuldade da revisao
- [x] Simulados com desempenho por disciplina e estrategia de prova
- [x] Cronometro em modo prova real
- [x] Aviso de simulado por frequencia configuravel (com adiar, sem criar nada)
- [x] Desempenho do ultimo simulado como sinal nas sugestoes de ajuste
- [x] Dashboard de desempenho (geral, disciplina, assunto, evolucao, erros)
- [x] Graficos leves em SVG (sem biblioteca)
- [x] Ciclo adaptativo com sugestoes justificadas e aceite explicito

### Fase 3
- [x] TAF: testes, marcas, evolucao e planejamento de treinos
- [x] Faculdade: disciplinas, atividades e horas semanais
- [x] Relatorio de fechamento de ciclo com analise e sugestoes

### Fase 4
- [x] Exportacao CSV e JSON
- [x] Importacao CSV com validacao de colunas
- [x] Backup e restauracao do SQLite pela interface e pela CLI
- [x] Layout responsivo (desktop-first, funcional no celular)
- [ ] Integracao opcional com Google Calendar - **adiada**, ver abaixo

### Fase 5 - Acesso remoto
- [x] Fuso horario configuravel (`PRF_TIMEZONE`), independente do relogio do servidor
- [x] Login de usuario unico com senha em hash, fora do banco e dos backups
- [x] Recusa de servir se publicado sem senha ou com a chave de exemplo
- [x] Bloqueio por tentativas, cookie endurecido e verificacao de origem (CSRF)
- [x] Guia de publicacao gratuita no PythonAnywhere ([DEPLOY.md](DEPLOY.md))

### Fase 6 - Treinos estruturados
- [x] Treino como plano reutilizavel com objetivo e vigencia
- [x] Exercicios individuais com prescricao flexivel por tipo
- [x] Reordenar, duplicar e excluir exercicios
- [x] Modo de execucao guiado, exercicio a exercicio e serie a serie
- [x] Registro de resultado por serie, separado da prescricao
- [x] Historico de execucoes com prescrito x realizado
- [x] Migration convertendo os treinos do formato antigo sem perda de dados

## Adiado com motivo

### Google Calendar
Exigiria OAuth com `credentials.json`, tela de consentimento no Google Cloud e um fluxo de
refresh token - configuracao complexa demais frente ao ganho, e o proprio projeto define
que o sistema nao pode depender da agenda. O que a integracao traria (ver plantoes e
compromissos) nao melhora diretamente o estudo.

Se um dia for feita, as regras sao: opcional, sem nunca criar um evento por revisao nem
por bloco do ciclo, e o sistema continua funcionando integralmente sem ela.

### FSRS / SM-2
A revisao usa intervalos configuraveis com ajuste por dificuldade. Um algoritmo adaptativo
de verdade ganharia pouco no volume de um concurso e custaria previsibilidade - o usuario
precisa entender de onde veio cada data. Reavaliar so se a fila comecar a ficar
visivelmente mal calibrada com o uso real.

## Ideias para depois (nao comprometidas)

Cada item so entra se responder "sim" a: *isso melhora diretamente o estudo?*

- Filtro por ciclo nas telas de sessoes e questoes (hoje o filtro e por periodo)
- Comparativo lado a lado entre dois simulados
- Marcar dias de plantao/folga para a media de questoes por folga sair automatica
  (hoje o numero de folgas vem de Configuracoes)
- Exportar o relatorio de ciclo em PDF (hoje da para imprimir - o CSS ja trata `@media print`)
- Anexar o enunciado da questao ao caderno de erros (imagem/arquivo)
- Atalhos de teclado no Painel para registrar sem tirar a mao do teclado

## Nao sera feito

- Login, multiusuario, nuvem
- Gamificacao (XP, moedas, medalhas, ranking)
- Notificacoes ou jobs em segundo plano que alterem datas
- Qualquer automacao que mude o planejamento sem clique do usuario
