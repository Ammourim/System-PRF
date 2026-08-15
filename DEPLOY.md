# Publicar no PythonAnywhere (gratuito)

Guia para acessar o Sistema PRF do celular, de qualquer lugar, sem custo.
Leva cerca de 30 minutos na primeira vez. Depois, atualizar sao dois comandos.

## Por que PythonAnywhere

O plano gratuito tem **disco persistente** (512 MiB), entao o `prf.db` sobrevive a
reinicios - o que nao acontece em Render, Netlify, Vercel e afins, onde o disco e efemero
e cada sessao de estudo registrada desapareceria. O limite de 100 CPU-segundos **nao se
aplica a web apps**, so a consoles e tarefas agendadas.

Contrapartidas, para voce saber de antemao:

* o app expira apos **1 mes** sem renovacao - basta entrar no painel e clicar em um botao.
  **Nenhum dado e apagado** se voce esquecer; o site so para de responder ate voce renovar;
* sem dominio proprio no plano gratuito (o endereco sera `SEUUSUARIO.pythonanywhere.com`);
* seus dados de estudo ficam em um servidor de terceiros.

---

## Parte 1 - Codigo no GitHub (repositorio privado)

1. Crie uma conta em <https://github.com> e um repositorio **privado** chamado `System-PRF`.
   Nao marque nenhuma opcao de inicializacao.

2. No seu PC, dentro da pasta do projeto:

```bash
git init -b main
```

```bash
git add . && git commit -m "Sistema PRF"
```

```bash
git remote add origin https://github.com/SEUUSUARIO/System-PRF.git
```

```bash
git push -u origin main
```

O `.gitignore` ja impede que `.env`, `data/*.db` e `backups/` subam - suas senhas e seus
dados de estudo **nao vao para o GitHub**.

3. Gere um **token de acesso** para o servidor poder baixar o repositorio privado:
   GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens →
   *Generate new token*, com acesso de **leitura** apenas a este repositorio. Guarde o token.

## Parte 2 - Conta e codigo no PythonAnywhere

4. Crie a conta gratuita em <https://www.pythonanywhere.com> (plano **Beginner**).

5. Abra **Consoles → Bash** e baixe o projeto (o token entra no lugar da senha):

```bash
git clone https://github.com/SEUUSUARIO/System-PRF.git
```

6. Crie o ambiente virtual e instale as dependencias:

```bash
python3.11 -m venv ~/System-PRF/.venv
```

```bash
~/System-PRF/.venv/bin/pip install -r ~/System-PRF/requirements.txt
```

## Parte 3 - Senha e configuracao

7. Ainda no console Bash, gere o hash da senha (a senha em texto puro nunca e gravada):

```bash
cd ~/System-PRF && .venv/bin/python -m flask --app run:app set-password
```

8. Crie o arquivo `.env` com o que o comando imprimiu:

```bash
nano ~/System-PRF/.env
```

Conteudo (cole o hash e a chave gerados no passo anterior):

```text
PRF_SECRET_KEY=cole-aqui-a-chave-gerada
PRF_PASSWORD_HASH=cole-aqui-o-hash-gerado
PRF_TIMEZONE=America/Sao_Paulo
PRF_HTTPS=1
PRF_DEBUG=0
```

Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.

> **Nao pule este passo.** Se a aplicacao for publicada sem `PRF_PASSWORD_HASH`, ela se
> recusa a responder para enderecos externos e mostra uma tela explicando o que falta -
> de proposito, para nunca ficar aberta por esquecimento.

## Parte 4 - Web app

9. Va em **Web → Add a new web app** → *Manual configuration* → **Python 3.11**.

10. Em **Virtualenv**, informe:

```text
/home/SEUUSUARIO/System-PRF/.venv
```

11. Em **Code → WSGI configuration file**, clique no link e **apague todo o conteudo**,
    substituindo pelo do arquivo `wsgi_pythonanywhere.py` deste projeto (troque
    `SEUUSUARIO` pelo seu usuario). Salve.

12. Em **Static files**, adicione o mapeamento para o CSS e o JS carregarem:

| URL | Directory |
| --- | --- |
| `/static/` | `/home/SEUUSUARIO/System-PRF/app/static/` |

13. Clique no botao verde **Reload**. Abra `https://SEUUSUARIO.pythonanywhere.com` -
    deve aparecer a tela de senha.

O banco e criado sozinho no primeiro acesso, com as 14 disciplinas, as configuracoes
padrao e o Ciclo #01 - **sem** dados de demonstracao.

## Parte 5 - Levar seus dados atuais (opcional)

Se quiser continuar de onde parou no PC:

1. No sistema local, va em **Dados e backup → Gerar backup agora** e baixe o `.db`.
2. No PythonAnywhere, **Files** → entre em `System-PRF/data/` → *Upload a file*.
3. Renomeie o arquivo enviado para `prf.db` (apagando o que existir) e clique em **Reload**.

---

## Uso diario

Abra `https://SEUUSUARIO.pythonanywhere.com` no celular, digite a senha uma vez e pronto -
a sessao dura **30 dias**, entao voce nao vai redigitar a senha a cada plantao. No Android
e no iOS da para usar "Adicionar a tela de inicio" e o sistema abre como um aplicativo.

## Atualizar depois de mexer no codigo

No PC:

```bash
git add . && git commit -m "descricao da mudanca" && git push
```

No console Bash do PythonAnywhere:

```bash
cd ~/System-PRF && git pull
```

Depois clique em **Reload** na aba Web. Se houver dependencia nova, rode antes
`~/System-PRF/.venv/bin/pip install -r ~/System-PRF/requirements.txt`.

Migrations de banco sao aplicadas sozinhas no Reload.

## Manutencao

| Quando | O que fazer |
| --- | --- |
| **Todo mes** | Entrar no painel do PythonAnywhere e clicar em renovar o web app (a aba **Web** avisa). Nada e apagado se atrasar. |
| **Toda semana** | **Dados e backup → Gerar backup agora** e baixar o arquivo para o PC. O plano gratuito nao tem backup automatico. |
| **Trocar a senha** | Rodar `set-password` de novo, atualizar o `.env` e dar **Reload**. |

## Se algo der errado

* **Erro 502 / pagina em branco**: veja **Web → Error log**. Quase sempre e caminho errado
  no arquivo WSGI ou virtualenv nao configurado.
* **Site sem formatacao**: o mapeamento de *Static files* (passo 12) esta faltando ou errado.
* **"Nenhuma senha definida"**: falta `PRF_PASSWORD_HASH` no `.env`, ou faltou dar Reload.
* **Erro sobre `PRF_SECRET_KEY`**: a chave ainda e a de exemplo. Gere uma com
  `python -c "import secrets; print(secrets.token_hex(32))"`.
* **Datas erradas por um dia**: `PRF_TIMEZONE` nao chegou na aplicacao. Confirme a linha no
  `.env` e no arquivo WSGI.

## Seguranca

O que protege o sistema publicado:

* senha guardada apenas como **hash** no `.env` - fora do banco, dos backups e das
  exportacoes, e fora do GitHub;
* bloqueio de 15 minutos apos 5 tentativas erradas;
* cookie de sessao `HttpOnly`, `Secure` e `SameSite=Lax`;
* verificacao de origem em toda escrita (protecao contra CSRF);
* recusa de servir se for publicado sem senha ou com a chave de exemplo.

Use uma senha que voce nao use em nenhum outro lugar.
