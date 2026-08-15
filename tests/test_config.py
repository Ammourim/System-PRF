"""Leitura do .env - inclusive os arquivos que o Windows gera com BOM."""

import os

from app.config import load_dotenv


def _load(tmp_path, content, encoding="utf-8"):
    path = tmp_path / ".env"
    path.write_text(content, encoding=encoding)
    load_dotenv(path)
    return path


def test_le_variaveis_simples(tmp_path, monkeypatch):
    monkeypatch.delenv("PRF_TESTE_A", raising=False)
    _load(tmp_path, "PRF_TESTE_A=valor\n")
    assert os.environ["PRF_TESTE_A"] == "valor"


def test_le_arquivo_com_bom(tmp_path, monkeypatch):
    """Bloco de Notas e PowerShell gravam UTF-8 com BOM.

    Sem tratamento, a primeira variavel do arquivo seria perdida em silencio.
    """
    monkeypatch.delenv("PRF_TESTE_BOM", raising=False)
    _load(tmp_path, "PRF_TESTE_BOM=primeiro\n", encoding="utf-8-sig")
    assert os.environ["PRF_TESTE_BOM"] == "primeiro"


def test_ignora_comentarios_e_linhas_vazias(tmp_path, monkeypatch):
    monkeypatch.delenv("PRF_TESTE_B", raising=False)
    _load(tmp_path, "# comentario\n\nPRF_TESTE_B=ok\n")
    assert os.environ["PRF_TESTE_B"] == "ok"


def test_remove_aspas(tmp_path, monkeypatch):
    monkeypatch.delenv("PRF_TESTE_C", raising=False)
    _load(tmp_path, 'PRF_TESTE_C="com aspas"\n')
    assert os.environ["PRF_TESTE_C"] == "com aspas"


def test_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    monkeypatch.setenv("PRF_TESTE_D", "do ambiente")
    _load(tmp_path, "PRF_TESTE_D=do arquivo\n")
    assert os.environ["PRF_TESTE_D"] == "do ambiente"


def test_valor_com_sinal_de_igual(tmp_path, monkeypatch):
    """Hashes de senha contem '=' - nao podem ser cortados."""
    monkeypatch.delenv("PRF_TESTE_E", raising=False)
    _load(tmp_path, "PRF_TESTE_E=scrypt:32768:8:1$abc$def==\n")
    assert os.environ["PRF_TESTE_E"] == "scrypt:32768:8:1$abc$def=="


def test_arquivo_inexistente_nao_quebra(tmp_path):
    load_dotenv(tmp_path / "nao-existe.env")
