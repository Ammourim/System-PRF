# Publicar no PythonAnywhere (gratuito)

Guia para acessar o Sistema PRF do celular, de qualquer lugar, sem custo.

**Todos os comandos abaixo sao exatos: copie e cole sem alterar nada.**
Os que rodam no servidor usam `~` (sua pasta pessoal), entao funcionam qualquer que seja
seu nome de usuario no PythonAnywhere.

Onde cada comando roda esta indicado assim:

* 💻 **No seu PC** - Prompt de Comando, dentro de `C:\Users\ALAN\Documents\System-PRF`
* ☁️ **No PythonAnywhere** - menu **Consoles → Bash**

---

## Ja comecou e travou? Comece por aqui

Se voce ja rodou `git clone` no PythonAnywhere e apareceu
`You appear to have cloned an empty repository`, o codigo ainda nao tinha chegado ao
GitHub naquele momento. Nao clone de novo - basta atualizar a copia existente:

☁️ **No PythonAnywhere:**

```bash
cd ~/System-PRF && git pull origin main && ls
```

Se aparecer a lista de arquivos (`app`, `run.py`, `requirements.txt`...), esta resolvido.
Pule para a **Parte 3**.

Se aparecer `Already up to date` e a pasta seguir vazia, o codigo nao subiu do PC. Volte a
Parte 1.

---

## Parte 1 - Enviar o codigo para o GitHub

💻 **No seu PC**, verifique se ja esta tudo enviado:

```bash
git status && git log origin/main..main --oneline
```

Se a segunda parte nao imprimir nenhuma linha, **ja esta tudo no GitHub** - siga para a
Parte 2.

Se imprimir alguma linha, envie:

```bash
git push -u origin main
```

Abre uma janela do navegador para entrar no GitHub; e so autorizar. **Nao e preciso token
para enviar do seu PC.**

Conferencia de seguranca - este comando **nao pode imprimir nada**:

```bash
git ls-files | findstr /R "^\.env$ \.db$"
```

Se nao imprimiu nada, sua senha e seus dados de estudo nao foram para o GitHub.

## Parte 2 - Baixar o codigo no servidor

1. Crie a conta gratuita em <https://www.pythonanywhere.com> (plano **Beginner**).

2. ☁️ **No PythonAnywhere**, abra **Consoles → Bash** e rode:

```bash
git clone https://github.com/ammourim/System-PRF.git ~/System-PRF
```

Como o repositorio e **publico**, isso funciona sem senha e sem token.

> **Se voce tornar o repositorio privado** (GitHub → Settings → *Change repository
> visibility*), passara a ser necessario um token: GitHub → **Settings** → **Developer
> settings** → **Personal access tokens** → **Fine-grained tokens** → *Generate new token*,
> com *Only select repositories* → `System-PRF` e *Contents: **Read-only***. No `git clone`,
> informe `ammourim` como `Username` e **cole o token** como `Password` (nada aparece na
> tela enquanto cola - e normal).

3. Confirme que os arquivos chegaram:

```bash
ls ~/System-PRF
```

Se aparecer `destination path 'System-PRF' already exists`, a pasta ja existe de uma
tentativa anterior. Nao clone de novo - atualize:

```bash
cd ~/System-PRF && git pull origin main && ls
```

## Parte 3 - Ambiente e dependencias

4. ☁️ **No console Bash do PythonAnywhere**, crie o ambiente e instale as dependencias
   (o segundo comando demora cerca de um minuto):

```bash
python3.11 -m venv ~/System-PRF/.venv
```

```bash
~/System-PRF/.venv/bin/pip install -r ~/System-PRF/requirements.txt
```

Ao final deve aparecer `Successfully installed Flask ... tzdata ...`.

## Parte 4 - Senha e configuracao

5. ☁️ Gere o hash da senha (a senha em texto puro nunca e gravada):

```bash
cd ~/System-PRF && .venv/bin/python -m flask --app run:app set-password
```

Digite a senha duas vezes (nao aparece na tela). O comando imprime uma ou duas linhas
comecando com `PRF_PASSWORD_HASH=` e `PRF_SECRET_KEY=`. **Copie-as.**

6. ☁️ Crie o arquivo `.env`:

```bash
nano ~/System-PRF/.env
```

Cole exatamente isto, substituindo as duas primeiras linhas pelas que o comando gerou:

```text
PRF_SECRET_KEY=cole-aqui-a-chave-gerada
PRF_PASSWORD_HASH=cole-aqui-o-hash-gerado
PRF_TIMEZONE=America/Sao_Paulo
PRF_HTTPS=1
PRF_DEBUG=0
```

Salve: `Ctrl+O` → `Enter` → `Ctrl+X`.

7. ☁️ Confira se ficou correto (deve imprimir 5 linhas, com as duas primeiras longas):

```bash
cut -c1-40 ~/System-PRF/.env
```

> **Nao pule este passo.** Publicada sem `PRF_PASSWORD_HASH`, a aplicacao se recusa a
> responder para enderecos externos e mostra uma tela explicando o que falta - de proposito,
> para nunca ficar aberta por esquecimento.

## Parte 5 - Criar o web app

Esta parte alterna entre o **console Bash** e a **aba Web** do navegador. Preste atencao ao
icone de cada passo.

> ⚠️ **Os comandos ☁️ so funcionam no console Bash do PythonAnywhere.**
> Rodados no seu PC eles **nao dao erro** - o `$HOME` do Windows vale `C:\Users\ALAN` e o
> resultado seria um caminho de aparencia correta, mas errado, que faz o site nao subir.
> Na duvida, confirme onde voce esta: o console do PythonAnywhere responde `/home/...` a
> este comando:
>
> ```bash
> pwd
> ```

### 5a - Coletar os dois caminhos (☁️ console Bash)

8. ☁️ **No console Bash do PythonAnywhere** (o mesmo do `git clone` e do `pip install`),
   rode e **deixe a saida na tela** - ela sera usada nos passos 10 e 11:

```bash
echo "Virtualenv:   $HOME/System-PRF/.venv" && echo "Static dir:   $HOME/System-PRF/app/static/"
```

A saida deve comecar com `/home/`, assim:

```text
Virtualenv:   /home/seu-usuario/System-PRF/.venv
Static dir:   /home/seu-usuario/System-PRF/app/static/
```

Se aparecer `C:\Users\...`, voce rodou no PC - repita no console do PythonAnywhere.

### 5b - Configurar a aba Web (🌐 navegador)

9. 🌐 Menu **Web** → **Add a new web app** → **Next** → **Manual configuration**
   (nao escolha "Flask") → **Python 3.11** → **Next**.

10. 🌐 Secao **Virtualenv**: clique em *Enter path to a virtualenv* e cole **so o caminho**
    da linha `Virtualenv` do passo 8 (sem o rotulo `Virtualenv:` e sem os espacos).
    Confirme no visto azul.

11. 🌐 Secao **Static files**: clique em *Enter URL* e preencha as duas colunas:

| Campo | Valor |
| --- | --- |
| URL | `/static/` |
| Directory | o caminho da linha `Static dir` do passo 8 |

Sem isso o site abre sem formatacao nenhuma.

12. 🌐 Secao **Code** → clique em **WSGI configuration file**. **Apague todo o conteudo** e
    cole o conteudo do arquivo `wsgi_pythonanywhere.py` deste projeto. Nao ha nada para
    editar nele. Clique em **Save**.

    Para ver o conteudo, abra o arquivo no menu **Files** ou rode ☁️ no console:

```bash
cat ~/System-PRF/wsgi_pythonanywhere.py
```

13. 🌐 Volte ao topo da aba **Web** e clique no botao verde **Reload**.

### 5c - Testar

14. ☁️ Descubra o endereco do seu site:

```bash
echo https://$(whoami).pythonanywhere.com
```

Abra esse endereco no navegador - deve aparecer a **tela de senha**. Se quiser confirmar
que a aplicacao subiu antes de logar, acrescente `/saude` ao endereco: deve responder
`{"ok":true}`.

O banco e criado sozinho no primeiro acesso, com as 14 disciplinas, as configuracoes padrao
e o Ciclo #01 - **sem** dados de demonstracao.

## Parte 6 - Levar seus dados atuais (opcional)

Se quiser continuar de onde parou no PC:

1. 💻 No sistema local, **Dados e backup → Gerar backup agora** e baixe o `.db`.
2. Menu **Files** no PythonAnywhere → entre em `System-PRF/data/` → **Upload a file**.
3. ☁️ Renomeie o arquivo enviado (troque `prf-AAAAMMDD-HHMMSS.db` pelo nome real):

```bash
cd ~/System-PRF/data && mv prf-AAAAMMDD-HHMMSS.db prf.db
```

4. Clique em **Reload** na aba Web.

---

## Uso diario

Abra o endereco no celular, digite a senha uma vez e pronto - a sessao dura **30 dias**,
entao voce nao vai redigitar a senha a cada plantao. No Android e no iOS, use "Adicionar a
tela de inicio" e ele abre como um aplicativo.

## Atualizar depois de mexer no codigo

💻 **No seu PC:**

```bash
git add . && git commit -m "descricao da mudanca" && git push
```

☁️ **No PythonAnywhere:**

```bash
cd ~/System-PRF && git pull && .venv/bin/pip install -r requirements.txt
```

Depois clique em **Reload** na aba **Web**. Migrations de banco sao aplicadas sozinhas.

## Manutencao

| Quando | O que fazer |
| --- | --- |
| **Todo mes** | Aba **Web** → clicar no botao de renovar o web app. Nada e apagado se atrasar; o site so para de responder ate voce renovar. |
| **Toda semana** | **Dados e backup → Gerar backup agora** e baixar o arquivo para o PC. O plano gratuito nao tem backup automatico. |
| **Trocar a senha** | Repetir os passos 5 e 6 e dar **Reload**. |

---

## Se algo der errado

### No Git / GitHub

* **`Repository not found` mostrando `SEUUSUARIO`**: o endereco ficou com o texto de
  exemplo. Corrija (💻 no PC):

```bash
git remote set-url origin https://github.com/ammourim/System-PRF.git
```

* **`error: remote origin already exists`**: o `origin` ja existe. Use o `set-url` acima,
  nao `git remote add`.

* **`You appear to have cloned an empty repository`**: o codigo ainda nao estava no GitHub
  quando voce clonou. Faca o push no PC e depois, no servidor:
  `cd ~/System-PRF && git pull origin main`.

* **`destination path 'System-PRF' already exists`**: a pasta ja existe. Nao clone de novo -
  use `cd ~/System-PRF && git pull origin main`.

* **`nothing to commit, working tree clean`**: nao e erro, o commit ja existe. Siga para o push.

* **`Updates were rejected`**: o repositorio foi criado com README. Rode
  `git pull --rebase origin main` e depois o push.

### No PythonAnywhere

* **Erro 502 / pagina em branco**: **Web → Error log** (o link fica no fim da aba). Quase
  sempre e caminho errado no WSGI ou virtualenv nao configurado.
* **Site sem formatacao**: falta o mapeamento de *Static files* (passo 11).
* **`ModuleNotFoundError: No module named 'flask'`**: o campo Virtualenv esta vazio ou
  errado (passo 10), ou o `pip install` da Parte 3 nao rodou.
* **"Nenhuma senha definida"**: falta `PRF_PASSWORD_HASH` no `.env`, ou faltou dar Reload.
* **Erro sobre `PRF_SECRET_KEY`**: a chave ainda e a de exemplo. Rode o passo 5 de novo.
* **Datas erradas por um dia**: `PRF_TIMEZONE` nao chegou na aplicacao. Confira o `.env`
  (passo 7) e o conteudo do arquivo WSGI (passo 12).

## Seguranca

* senha guardada apenas como **hash** no `.env` - fora do banco, dos backups, das
  exportacoes e do GitHub;
* bloqueio de 15 minutos apos 5 tentativas erradas;
* cookie de sessao `HttpOnly`, `Secure` e `SameSite=Lax`;
* verificacao de origem em toda escrita (protecao contra CSRF);
* recusa de servir se publicado sem senha ou com a chave de exemplo.

Use uma senha que voce nao use em nenhum outro lugar.
