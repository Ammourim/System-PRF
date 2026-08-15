"""Baixa o banco do servidor e guarda uma copia local verificada.

Roda no SEU PC (nao no servidor). Usa a API oficial do PythonAnywhere, que
autentica por token - a senha da conta nunca e usada nem guardada.

Uso:
    python scripts/backup_remoto.py

O token e lido, nesta ordem:
  1. variavel de ambiente PRF_PA_TOKEN
  2. arquivo .pa_token na raiz do projeto (uma linha, so o token)

Para obter o token: PythonAnywhere -> Account -> aba "API token".

O que ele faz:
  * baixa data/prf.db do servidor;
  * VERIFICA a integridade do arquivo baixado (backup que nao abre nao e backup);
  * guarda em backups/ com data e hora no nome;
  * apaga os mais antigos, mantendo os N ultimos;
  * avisa quantos dias faltam para o web app expirar.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API = "https://www.pythonanywhere.com/api/v0"

USUARIO = "nalamiroma28"
DOMINIO = "nalamiroma28.pythonanywhere.com"
CAMINHO_REMOTO = f"/home/{USUARIO}/System-PRF/data/prf.db"
MANTER = 12  # quantos backups guardar


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
        "Pegue o seu em PythonAnywhere -> Account -> aba 'API token' e entao:\n"
        f"  grave-o no arquivo {BASE_DIR / '.pa_token'}\n"
        "  ou defina a variavel de ambiente PRF_PA_TOKEN."
    )


def chamar(caminho: str, token: str, binario: bool = False):
    requisicao = urllib.request.Request(
        f"{API}{caminho}", headers={"Authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(requisicao, timeout=120) as resposta:
            dados = resposta.read()
    except urllib.error.HTTPError as erro:
        if erro.code == 401:
            sys.exit("Token invalido ou expirado. Gere outro na aba 'API token'.")
        if erro.code == 404:
            sys.exit(f"Nao encontrado no servidor: {caminho}\n"
                     "O banco so existe depois do primeiro acesso ao site.")
        sys.exit(f"Erro HTTP {erro.code} em {caminho}: {erro.read()[:200]!r}")
    except urllib.error.URLError as erro:
        sys.exit(f"Falha de rede: {erro.reason}")
    return dados if binario else json.loads(dados)


def verificar_sqlite(caminho: Path) -> tuple[bool, str]:
    """Um backup que nao abre nao e backup. Confere antes de considerar valido."""
    try:
        conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            if conexao.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False, "integrity_check falhou"
            sessoes = conexao.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
            questoes = conexao.execute(
                "SELECT COALESCE(SUM(total), 0) FROM questions").fetchone()[0]
            disciplinas = conexao.execute("SELECT COUNT(*) FROM disciplines").fetchone()[0]
        finally:
            conexao.close()
    except sqlite3.Error as erro:
        return False, f"nao abriu como SQLite: {erro}"
    return True, f"{disciplinas} disciplinas, {sessoes} sessoes, {questoes} questoes"


def rotacionar(pasta: Path, manter: int) -> int:
    arquivos = sorted(pasta.glob("prf-remoto-*.db"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    removidos = 0
    for antigo in arquivos[manter:]:
        antigo.unlink()
        removidos += 1
    return removidos


def avisar_expiracao(token: str) -> None:
    dados = chamar(f"/user/{USUARIO}/webapps/{DOMINIO}/", token)
    expiry = dados.get("expiry")
    if not expiry:
        return
    try:
        data = datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date()
    except ValueError:
        print(f"Expiracao do site: {expiry}")
        return
    faltam = (data - datetime.now().date()).days
    aviso = "  <<< RENOVE JA" if faltam <= 7 else ""
    print(f"Site expira em {data.strftime('%d/%m/%Y')} "
          f"({faltam} dia(s)){aviso}")
    if faltam <= 7:
        print("  Abra https://www.pythonanywhere.com/user/"
              f"{USUARIO}/webapps/ e clique em 'Run until 1 month from today'.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do Sistema PRF hospedado.")
    parser.add_argument("--manter", type=int, default=MANTER,
                        help=f"quantos backups guardar (padrao {MANTER})")
    parser.add_argument("--destino", default=str(BASE_DIR / "backups"),
                        help="pasta onde salvar")
    args = parser.parse_args()

    token = ler_token()
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)

    print(f"Baixando {CAMINHO_REMOTO} ...")
    conteudo = chamar(f"/user/{USUARIO}/files/path{CAMINHO_REMOTO}", token, binario=True)

    # Grava primeiro em arquivo temporario: so vira backup depois de verificado.
    with tempfile.NamedTemporaryFile(delete=False, dir=destino, suffix=".parcial") as tmp:
        tmp.write(conteudo)
        temporario = Path(tmp.name)

    ok, detalhe = verificar_sqlite(temporario)
    if not ok:
        temporario.unlink(missing_ok=True)
        print(f"BACKUP DESCARTADO: {detalhe}", file=sys.stderr)
        return 1

    alvo = destino / f"prf-remoto-{datetime.now():%Y%m%d-%H%M%S}.db"
    temporario.replace(alvo)
    print(f"OK  {alvo.name}  ({len(conteudo) / 1024:.0f} KB) - {detalhe}")

    removidos = rotacionar(destino, args.manter)
    if removidos:
        print(f"Removidos {removidos} backup(s) antigo(s); mantidos {args.manter}.")

    try:
        avisar_expiracao(token)
    except SystemExit:
        raise
    except Exception as erro:  # o aviso nunca pode invalidar um backup bem-sucedido
        print(f"(nao consegui checar a expiracao: {erro})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
