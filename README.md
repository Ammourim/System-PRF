# Sistema PRF

Sistema pessoal de organizacao de estudos para a preparacao ao concurso da Policia
Rodoviaria Federal. Roda **localmente**, em um unico arquivo SQLite, sem nuvem e sem
conta de usuario.

O principio do sistema e simples:

> **CICLO FLEXIVEL + REGISTRO MANUAL + QUESTOES + REVISAO ESPACADA + SIMULADOS + FEEDBACK.**

O sistema **recomenda**, nunca **impoe**. Nenhuma automacao altera seu planejamento sem
voce clicar. Perder um dia nao gera pendencia, nao reinicia o ciclo e nao muda nenhuma data.

---

## Instalacao

Requisitos: **Python 3.11 ou superior** (testado no 3.14). Nada alem disso.

```bash
python -m venv .venv
```

Ative o ambiente virtual:

```bash
.venv\Scripts\activate
```

Instale as dependencias (apenas Flask e pytest):

```bash
pip install -r requirements.txt
```

## Execucao

```bash
python run.py
```

Abra <http://127.0.0.1:5000> no navegador. Na primeira execucao o sistema cria o banco em
`data/prf.db`, cadastra as 14 disciplinas, as configuracoes padrao e o **Ciclo #01** - da
para comecar a estudar imediatamente.

Para deixar um atalho no Windows, crie um arquivo `iniciar.bat` com:

```bat
@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe run.py
```

## Configuracao

Tudo que envolve metas, blocos, intervalos e limiares fica na tela **Configuracoes** -
nada esta fixo no codigo. O arquivo `.env` (opcional) trata apenas de infraestrutura:

```bash
copy .env.example .env
```

| Variavel | Padrao | Para que serve |
| --- | --- | --- |
| `PRF_SECRET_KEY` | `dev-local-somente` | Assina a sessao e o login. Troque ao publicar. |
| `PRF_PASSWORD_HASH` | vazio | Hash da senha de acesso. Vazio = modo local sem login. |
| `PRF_TIMEZONE` | `America/Sao_Paulo` | Fuso usado em todas as datas. |
| `PRF_HTTPS` | `0` | `1` quando servido por HTTPS (marca o cookie como Secure). |
| `PRF_DATABASE` | `data/prf.db` | Caminho do banco. |
| `PRF_BACKUP_DIR` | `backups/` | Pasta dos backups. |
| `PRF_HOST` / `PRF_PORT` | `127.0.0.1` / `5000` | Endereco do servidor local. |
| `PRF_DEBUG` | `0` | `1` liga o recarregamento automatico (so em desenvolvimento). |

Gere uma chave com:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Acessar de qualquer lugar

Para usar no celular durante os plantoes, veja **[DEPLOY.md](DEPLOY.md)**: publicacao
gratuita no PythonAnywhere, com senha, HTTPS e fuso correto. Leva ~30 minutos na primeira
vez; depois, atualizar sao dois comandos.

Defina a senha com:

```bash
python -m flask --app run:app set-password
```

## Banco de dados

SQLite unico em `data/prf.db`, criado e atualizado por **migrations** em
`app/migrations/*.sql`, aplicadas em ordem e registradas na tabela `schema_migrations`.
O detalhamento das tabelas esta em [DATABASE.md](DATABASE.md).

Comandos de manutencao:

```bash
python -m flask --app run:app init-db
```

```bash
python -m flask --app run:app seed-demo
```

```bash
python -m flask --app run:app backup
```

## Backup

Em **Dados e backup** voce pode:

* gerar um backup do SQLite (usa a API de backup do proprio SQLite, segura com WAL);
* baixar e restaurar qualquer backup (o estado atual e preservado em uma copia antes);
* exportar qualquer tabela em CSV e o banco inteiro em JSON;
* importar CSV para as tabelas de dados.

Backups ficam em `backups/` e estao no `.gitignore` - sao dados pessoais.

## Desenvolvimento

Testes:

```bash
python -m pytest
```

Conferir a sequencia do ciclo gerada pelas metas atuais:

```bash
python scripts/preview_cycle.py
```

Estrutura do codigo e decisoes de arquitetura: [ARCHITECTURE.md](ARCHITECTURE.md).
Como usar no dia a dia: [USER_GUIDE.md](USER_GUIDE.md).
O que ja existe e o que ficou de fora: [ROADMAP.md](ROADMAP.md).

## Dados de demonstracao

O sistema pode carregar um conjunto pequeno de dados de exemplo (sessoes, questoes, erros,
revisoes, um simulado, TAF e faculdade). Eles aparecem com a etiqueta `demo` e um aviso no
topo das telas, e podem ser removidos a qualquer momento em **Configuracoes -> Dados de
demonstracao**. Remover a demonstracao nao apaga suas disciplinas, configuracoes nem o ciclo.

## Seguranca

O sistema tem dois modos, decididos por `PRF_PASSWORD_HASH`:

* **Local** (sem senha): responde apenas em `127.0.0.1`, sem tela de login - o uso no PC
  continua sem atrito.
* **Publicado** (com senha): exige login em qualquer endereco.

Se a aplicacao for exposta a um endereco externo **sem** senha configurada, ela **se recusa
a responder** e mostra o que falta - por desenho, para nunca ficar aberta por esquecimento.
Da mesma forma, ela nao sobe com senha e a `SECRET_KEY` de exemplo, que tornaria o cookie
de sessao forjavel.

Outras medidas: senha guardada so como hash no `.env` (fora do banco, dos backups e das
exportacoes); bloqueio de 15 minutos apos 5 tentativas erradas; cookie `HttpOnly`,
`SameSite=Lax` e `Secure` sob HTTPS; verificacao de origem em toda escrita (CSRF); consultas
sempre parametrizadas; import/export restritos a uma lista branca de tabelas; `.env`,
`data/` e `backups/` no `.gitignore`.
