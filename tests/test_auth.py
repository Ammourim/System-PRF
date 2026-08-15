"""Testes de autenticacao, protecao CSRF e comportamento a prova de falha."""

import pytest

from app import create_app
from app.auth import make_hash

SENHA = "senha-de-teste-123"


@pytest.fixture()
def secure_app(tmp_path):
    """App como ficara publicado: com senha e chave propria."""
    return create_app({
        "DATABASE": str(tmp_path / "test.db"),
        "BACKUP_DIR": str(tmp_path / "backups"),
        "TESTING": True,
        "SECRET_KEY": "chave-propria-de-teste",
        "PASSWORD_HASH": make_hash(SENHA),
    })


@pytest.fixture()
def secure_client(secure_app):
    return secure_app.test_client()


def login(client, password=SENHA, **kwargs):
    return client.post("/entrar", data={"password": password}, **kwargs)


# ------------------------------------------------------ modo local (sem senha)
def test_sem_senha_em_localhost_libera(client):
    """O uso local de sempre nao pode ganhar atrito."""
    assert client.get("/").status_code == 200
    assert client.get("/questoes/").status_code == 200


def test_sem_senha_em_host_externo_recusa(client):
    """Publicado sem senha: recusa em vez de servir dados abertos."""
    response = client.get("/", headers={"Host": "meu-sistema.exemplo.com"})
    assert response.status_code == 503
    assert "Nenhuma senha definida" in response.get_data(as_text=True)


def test_recusa_vale_para_todas_as_rotas(client):
    for url in ["/questoes/", "/dados/", "/configuracoes/", "/desempenho/"]:
        response = client.get(url, headers={"Host": "externo.exemplo.com"})
        assert response.status_code == 503, url


def test_saude_responde_sem_login(client):
    assert client.get("/saude").get_json() == {"ok": True}


# ------------------------------------------------------------------- com senha
def test_com_senha_redireciona_para_login(secure_client):
    response = secure_client.get("/")
    assert response.status_code == 302
    assert "/entrar" in response.headers["Location"]


def test_login_correto_da_acesso(secure_client):
    assert login(secure_client).status_code == 302
    assert secure_client.get("/").status_code == 200
    assert secure_client.get("/questoes/").status_code == 200


def test_senha_errada_nao_da_acesso(secure_client):
    login(secure_client, password="errada")
    assert secure_client.get("/").status_code == 302


def test_sair_encerra_a_sessao(secure_client):
    login(secure_client)
    assert secure_client.get("/").status_code == 200
    secure_client.post("/sair")
    assert secure_client.get("/").status_code == 302


def test_login_volta_para_a_pagina_pedida(secure_client):
    response = secure_client.post(
        "/entrar", data={"password": SENHA, "next": "/revisoes/"})
    assert response.headers["Location"] == "/revisoes/"


def test_login_ignora_redirecionamento_externo(secure_client):
    """Nao permitir que 'next' leve para outro site."""
    response = secure_client.post(
        "/entrar", data={"password": SENHA, "next": "//site-malicioso.com"})
    assert "site-malicioso" not in response.headers["Location"]


def test_bloqueio_apos_tentativas(secure_client):
    from app import auth

    auth._attempts.clear()
    for _ in range(auth.MAX_ATTEMPTS):
        login(secure_client, password="errada")
    # Mesmo com a senha certa, o IP fica bloqueado por alguns minutos.
    login(secure_client)
    assert secure_client.get("/").status_code == 302
    auth._attempts.clear()


def test_login_correto_limpa_as_falhas(secure_client):
    from app import auth

    auth._attempts.clear()
    login(secure_client, password="errada")
    login(secure_client)
    assert secure_client.get("/").status_code == 200
    assert not auth._attempts
    auth._attempts.clear()


# ------------------------------------------------------------------------ CSRF
def test_post_de_outra_origem_e_recusado(secure_client):
    login(secure_client)
    response = secure_client.post(
        "/questoes/salvar",
        data={"date": "2026-08-15", "discipline_id": "1", "total": "10", "correct": "8"},
        headers={"Origin": "https://site-malicioso.com"})
    assert response.status_code == 400


def test_post_da_propria_origem_passa(secure_client, secure_app):
    login(secure_client)
    response = secure_client.post(
        "/questoes/salvar",
        data={"date": "2026-08-15", "discipline_id": "1", "total": "10", "correct": "8"},
        headers={"Origin": "http://localhost"})
    assert response.status_code == 302
    with secure_app.app_context():
        from app.db import scalar
        assert scalar("SELECT COUNT(*) FROM questions", (), 0) == 1


def test_referer_de_outra_origem_e_recusado(secure_client):
    login(secure_client)
    response = secure_client.post(
        "/questoes/salvar",
        data={"date": "2026-08-15", "discipline_id": "1", "total": "10", "correct": "8"},
        headers={"Referer": "https://site-malicioso.com/pagina"})
    assert response.status_code == 400


# --------------------------------------------------------------- configuracao
def test_recusa_subir_com_senha_e_chave_de_exemplo(tmp_path, monkeypatch):
    """Cookie assinado com a chave de exemplo seria forjavel."""
    monkeypatch.setenv("PRF_PASSWORD_HASH", make_hash(SENHA))
    monkeypatch.delenv("PRF_SECRET_KEY", raising=False)
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="PRF_SECRET_KEY"):
        create_app({"DATABASE": str(tmp_path / "x.db")})
