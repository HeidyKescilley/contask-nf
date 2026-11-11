"""Cadastro de escritório: aberto (local), por convite ou fechado (contas criadas pelo suporte no servidor)."""
from fastapi.testclient import TestClient

from tests.conftest import SENHA_TESTE


def _app(app_teste, monkeypatch, modo):
    from app.core import config as cfgmod
    monkeypatch.setenv("CONTASK_CADASTRO", modo)
    cfgmod.config.cache_clear()
    return TestClient(app_teste, base_url="http://127.0.0.1:8765")


def _cadastro(c, email="a@escritorio.com", **extra):
    return c.post("/api/auth/cadastrar", json={"nome": "Escritório A", "email": email, "senha": SENHA_TESTE, **extra})


def test_cadastro_fechado(app_teste, monkeypatch):
    with _app(app_teste, monkeypatch, "fechado") as c:
        assert c.get("/api/auth/eu").json()["cadastro"] == "fechado"
        r = _cadastro(c)
        assert r.status_code == 403 and "suporte" in r.json()["detail"]


def test_cadastro_por_convite_uso_unico(app_teste, monkeypatch):
    from app.core import convites
    from app.core.db import nova_sessao
    with _app(app_teste, monkeypatch, "convite") as c:
        assert _cadastro(c).status_code == 400
        with nova_sessao() as db:
            codigo = convites.gerar(db, "Escritório A")
            db.commit()
        assert len(codigo) == 19 and codigo.count("-") == 3
        r = _cadastro(c, convite=codigo.lower())
        assert r.status_code == 201, r.text
        c.post("/api/auth/sair")
        r = _cadastro(c, email="b@escritorio.com", convite=codigo)
        assert r.status_code == 400 and "já usado" in r.json()["detail"]


def test_ferramenta_cria_escritorios_separados(app_teste, monkeypatch, capsys):
    from sqlalchemy import select
    from app.core.db import nova_sessao
    from app.models import Usuario
    from app.tools import usuarios
    with _app(app_teste, monkeypatch, "fechado"):
        usuarios.main(["novo-escritorio", "Contábil Silva", "ana@silva.com", "Ana"])
        usuarios.main(["novo-escritorio", "Contábil Souza", "bia@souza.com", "Bia"])
        saida = capsys.readouterr().out
        assert "Senha inicial" in saida and "Contábil Souza" in saida
        with nova_sessao() as db:
            ana = db.scalar(select(Usuario).where(Usuario.email == "ana@silva.com"))
            bia = db.scalar(select(Usuario).where(Usuario.email == "bia@souza.com"))
            assert ana.escritorio_id != bia.escritorio_id and ana.trocar_senha
            esc_ana = ana.escritorio_id
        usuarios.main(["criar", "caio@silva.com", "Caio", "--escritorio", str(esc_ana)])
        with nova_sessao() as db:
            assert db.scalar(select(Usuario).where(Usuario.email == "caio@silva.com")).escritorio_id == esc_ana
        usuarios.main(["escritorios"])
        assert "2 usuário(s)" in capsys.readouterr().out
