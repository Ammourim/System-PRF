"""Publica o codigo no PythonAnywhere pela API oficial, do seu PC.

Roda no SEU PC. Usa a API oficial (autenticada por TOKEN - a senha da conta
nunca e usada nem guardada), na mesma linha do scripts/backup_remoto.py.

Uso:
    python scripts/deploy_pythonanywhere.py                 # do ultimo deploy ate HEAD
    python scripts/deploy_pythonanywhere.py --desde <sha>   # intervalo explicito
    python scripts/deploy_pythonanywhere.py --so-recarregar

O token e lido, nesta ordem:
  1. variavel de ambiente PRF_PA_TOKEN
  2. arquivo .pa_token na raiz do projeto (uma linha, so o token)

Ordem das etapas - a mais importante primeiro:

  1. BACKUP: baixa data/prf.db do servidor, verifica a integridade com
     PRAGMA integrity_check e guarda em backups/. Sem backup integro, o
     script para aqui e nao publica nada.
  2. COPIA DE SEGURANCA NO SERVIDOR: sobe o mesmo banco como
     data/prf-antes-<sha>.db, para o rollback nao depender do seu PC.
  3. CODIGO: envia os arquivos alterados no intervalo de commits.
     Preferencia por `git pull` (mantem o repositorio do servidor em dia);
     se nao houver console disponivel para isso, envia arquivo a arquivo.
  4. RELOAD do web app e conferencia de /saude.

As migrations sao aplicadas sozinhas no primeiro acesso apos o reload.
"""

from __future__ import annotations

import argparse
import json
import mimetypes  # noqa: F401  (mantido: multipart abaixo declara o tipo na mao)
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API = "https://www.pythonanywhere.com/api/v0"

USUARIO_PADRAO = "nalamiroma28"   # usuario do PythonAnywhere (no GitHub e "ammourim")
PASTA_REMOTA = "System-PRF"


# --------------------------------------------------------------------------
# Token e HTTP
# --------------------------------------------------------------------------
def ler_token() -> str:
    token = (os.environ.get("PRF_PA_TOKEN") or "").strip()
    if token:
        return token
    arquivo = BASE_DIR / ".pa_token"
    if arquivo.exists():
        token = arquivo.read_text(encoding="utf-8-sig").strip()
        if token:
            return token
    sys.exit(
        "Token nao encontrado.\n"
        "PythonAnywhere -> Account -> aba 'API token' -> Create a new API token.\n"
        f"Depois grave-o (so o token, uma linha) em: {BASE_DIR / '.pa_token'}\n"
        "O arquivo ja esta no .gitignore - nao vai para o GitHub."
    )


def pedir(caminho: str, token: str, metodo: str = "GET", dados: bytes | None = None,
          content_type: str | None = None, binario: bool = False, timeout: int = 120):
    cabecalhos = {"Authorization": f"Token {token}"}
    if content_type:
        cabecalhos["Content-Type"] = content_type
    requisicao = urllib.request.Request(
        f"{API}{caminho}", data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = resposta.read()
            status = resposta.status
    except urllib.error.HTTPError as erro:
        detalhe = erro.read()[:300]
        if erro.code == 401:
            sys.exit("Token invalido ou expirado. Gere outro na aba 'API token'.")
        if erro.code == 403:
            sys.exit(f"Token sem permissao para {caminho}. Detalhe: {detalhe!r}")
        raise RuntimeError(f"HTTP {erro.code} em {metodo} {caminho}: {detalhe!r}") from erro
    except urllib.error.URLError as erro:
        sys.exit(f"Falha de rede: {erro.reason}")
    if binario:
        return status, corpo
    if not corpo:
        return status, None
    try:
        return status, json.loads(corpo)
    except json.JSONDecodeError:
        return status, corpo


def multipart(campo: str, nome: str, conteudo: bytes) -> tuple[bytes, str]:
    """Corpo multipart/form-data minimo (a API de arquivos exige este formato)."""
    limite = f"----prf{uuid.uuid4().hex}"
    corpo = b"".join([
        f"--{limite}\r\n".encode(),
        f'Content-Disposition: form-data; name="{campo}"; filename="{nome}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        conteudo,
        f"\r\n--{limite}--\r\n".encode(),
    ])
    return corpo, f"multipart/form-data; boundary={limite}"


# --------------------------------------------------------------------------
# Git local
# --------------------------------------------------------------------------
def git(*args: str) -> str:
    resultado = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True)
    if resultado.returncode:
        sys.exit(f"git {' '.join(args)} falhou:\n{resultado.stderr.strip()}")
    return resultado.stdout.strip()


def arquivos_alterados(desde: str, ate: str = "HEAD") -> tuple[list[str], list[str]]:
    """(enviar, apagar) a partir do diff de commits."""
    enviar, apagar = [], []
    for linha in git("diff", "--name-status", f"{desde}..{ate}").splitlines():
        partes = linha.split("\t")
        estado, caminho = partes[0], partes[-1]
        (apagar if estado.startswith("D") else enviar).append(caminho)
    return enviar, apagar


# --------------------------------------------------------------------------
# Etapas
# --------------------------------------------------------------------------
def descobrir_webapp(usuario: str, token: str) -> str:
    _, apps = pedir(f"/user/{usuario}/webapps/", token)
    if not apps:
        sys.exit(f"Nenhum web app encontrado para '{usuario}'. Confira o usuario com --usuario.")
    dominio = apps[0]["domain_name"]
    if len(apps) > 1:
        print(f"  ! {len(apps)} web apps; usando o primeiro: {dominio}")
    return dominio


def baixar_banco(usuario: str, token: str, caminho_remoto: str) -> Path | None:
    try:
        _, dados = pedir(f"/user/{usuario}/files/path{caminho_remoto}", token, binario=True)
    except RuntimeError as erro:
        if "HTTP 404" in str(erro):
            print("  - Banco ainda nao existe no servidor (primeiro deploy). Seguindo.")
            return None
        raise

    destino_dir = BASE_DIR / "backups"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"prf-remoto-{datetime.now():%Y%m%d-%H%M%S}-antes-deploy.db"

    temporario = Path(tempfile.gettempdir()) / f"prf-check-{uuid.uuid4().hex}.db"
    temporario.write_bytes(dados)
    try:
        conexao = sqlite3.connect(str(temporario))
        try:
            estado = conexao.execute("PRAGMA integrity_check").fetchone()[0]
            tabelas = conexao.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        finally:
            conexao.close()
    except sqlite3.Error as erro:
        sys.exit(f"O banco baixado nao abre ({erro}). NADA foi publicado.")
    finally:
        if temporario.exists():
            temporario.unlink()

    if estado != "ok":
        sys.exit(f"integrity_check do banco baixado: {estado!r}. NADA foi publicado.")

    destino.write_bytes(dados)
    print(f"  OK backup local: {destino.name} ({len(dados) // 1024} KB, {tabelas} tabelas)")
    return destino


def copia_no_servidor(usuario: str, token: str, pasta: str, dados: bytes, marca: str) -> None:
    alvo = f"/home/{usuario}/{pasta}/data/prf-antes-{marca}.db"
    corpo, tipo = multipart("content", f"prf-antes-{marca}.db", dados)
    pedir(f"/user/{usuario}/files/path{alvo}", token, metodo="POST", dados=corpo,
          content_type=tipo, timeout=300)
    print(f"  OK copia no servidor: {alvo}")


def console_disponivel(usuario: str, token: str) -> int | None:
    """Console bash ja iniciado (a API nao consegue iniciar um do zero)."""
    _, consoles = pedir(f"/user/{usuario}/consoles/", token)
    for console in consoles or []:
        if console.get("executable", "").endswith("bash"):
            return console["id"]
    return None


def enviar_por_git(usuario: str, token: str, console_id: int, pasta: str) -> bool:
    comando = f"cd ~/{pasta} && git pull --ff-only && echo PRF_PULL_OK\n"
    try:
        pedir(f"/user/{usuario}/consoles/{console_id}/send_input/", token, metodo="POST",
              dados=json.dumps({"input": comando}).encode(),
              content_type="application/json")
    except RuntimeError as erro:
        print(f"  - Console nao aceitou comandos ({erro}). Enviando arquivo a arquivo.")
        return False

    for _ in range(20):
        time.sleep(3)
        _, saida = pedir(f"/user/{usuario}/consoles/{console_id}/get_latest_output/", token)
        texto = (saida or {}).get("output", "")
        if "PRF_PULL_OK" in texto:
            print("  OK git pull no servidor")
            return True
        if "error:" in texto or "fatal:" in texto:
            print("  - git pull reclamou; enviando arquivo a arquivo.")
            return False
    print("  - git pull sem resposta a tempo; enviando arquivo a arquivo.")
    return False


def enviar_arquivos(usuario: str, token: str, pasta: str,
                    enviar: list[str], apagar: list[str]) -> None:
    for relativo in enviar:
        local = BASE_DIR / relativo
        if not local.exists():
            print(f"  ! ignorado (nao existe localmente): {relativo}")
            continue
        alvo = f"/home/{usuario}/{pasta}/{relativo}"
        corpo, tipo = multipart("content", local.name, local.read_bytes())
        pedir(f"/user/{usuario}/files/path{alvo}", token, metodo="POST", dados=corpo,
              content_type=tipo, timeout=180)
        print(f"  + {relativo}")

    for relativo in apagar:
        alvo = f"/home/{usuario}/{pasta}/{relativo}"
        try:
            pedir(f"/user/{usuario}/files/path{alvo}", token, metodo="DELETE")
            print(f"  - {relativo}")
        except RuntimeError as erro:
            print(f"  ! nao consegui apagar {relativo}: {erro}")


def recarregar(usuario: str, token: str, dominio: str) -> None:
    pedir(f"/user/{usuario}/webapps/{dominio}/reload/", token, metodo="POST", timeout=180)
    print(f"  OK reload de {dominio}")


def conferir_saude(dominio: str) -> None:
    url = f"https://{dominio}/saude"
    for tentativa in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as resposta:
                corpo = resposta.read().decode("utf-8", "replace")
            print(f"  OK {url} -> {corpo.strip()[:80]}")
            return
        except Exception as erro:  # noqa: BLE001 - qualquer falha aqui e so informativa
            if tentativa == 4:
                print(f"  ! {url} nao respondeu: {erro}")
                print("    Veja Web -> Error log no PythonAnywhere.")
                return
            time.sleep(5)


# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Publica no PythonAnywhere pela API.")
    parser.add_argument("--usuario", default=USUARIO_PADRAO)
    parser.add_argument("--pasta", default=PASTA_REMOTA)
    parser.add_argument("--desde", default=None,
                        help="commit inicial do intervalo (padrao: penultimo commit)")
    parser.add_argument("--so-recarregar", action="store_true")
    parser.add_argument("--sem-backup", action="store_true",
                        help="pula o backup do banco (nao recomendado)")
    args = parser.parse_args()

    token = ler_token()
    usuario, pasta = args.usuario, args.pasta

    print(f"[1/5] Web app de '{usuario}'")
    dominio = descobrir_webapp(usuario, token)
    print(f"  {dominio}")

    if args.so_recarregar:
        print("[2/2] Reload")
        recarregar(usuario, token, dominio)
        conferir_saude(dominio)
        return

    caminho_banco = f"/home/{usuario}/{pasta}/data/prf.db"
    dados_banco = None
    print("[2/5] Backup do banco do servidor")
    if args.sem_backup:
        print("  - pulado por --sem-backup")
    else:
        copia = baixar_banco(usuario, token, caminho_banco)
        if copia:
            dados_banco = copia.read_bytes()

    marca = git("rev-parse", "--short", "HEAD")
    if dados_banco:
        print("[3/5] Copia de seguranca no servidor")
        copia_no_servidor(usuario, token, pasta, dados_banco, marca)
    else:
        print("[3/5] Copia de seguranca no servidor - nada a copiar")

    desde = args.desde or git("rev-parse", "--short", "HEAD~1")
    enviar, apagar = arquivos_alterados(desde)
    print(f"[4/5] Codigo ({desde}..HEAD): {len(enviar)} arquivo(s) a enviar,"
          f" {len(apagar)} a apagar")

    console_id = console_disponivel(usuario, token)
    if console_id and not apagar and enviar_por_git(usuario, token, console_id, pasta):
        pass
    else:
        if not console_id:
            print("  - Nenhum console bash aberto (a API nao inicia um). Enviando arquivos.")
        enviar_arquivos(usuario, token, pasta, enviar, apagar)
        print("  ! O repositorio git do servidor ficou 'sujo' (arquivos enviados por fora).")
        print("    Para resincronizar quando quiser, no console Bash do PythonAnywhere:")
        print(f"      cd ~/{pasta} && git fetch && git reset --hard origin/main")

    print("[5/5] Reload")
    recarregar(usuario, token, dominio)
    conferir_saude(dominio)
    print(f"\nPronto: https://{dominio}")
    print(f"Rollback do banco, se precisar: data/prf-antes-{marca}.db no servidor.")


if __name__ == "__main__":
    main()
