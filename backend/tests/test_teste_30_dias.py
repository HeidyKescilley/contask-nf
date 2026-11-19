"""Cadastro aberto pela página de vendas: 30 dias de teste grátis com tudo liberado."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import escritorios
from app.core.db import nova_sessao
from app.models import Escritorio
from tests.conftest import SENHA_TESTE
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401 (fixture)


@pytest.fixture()
def servidor(monkeypatch):
    """Como no servidor online: cadastro aberto, 30 dias de teste e teste completo (antes do app subir)."""
    monkeypatch.setenv("CONTASK_CADASTRO", "aberto")
    monkeypatch.setenv("CONTASK_CADASTRO_TESTE_DIAS", "30")
    monkeypatch.setenv("CONTASK_TESTE_COMPLETO", "true")


def _escritorio(cliente) -> Escritorio:
    esc = cliente.get("/api/auth/eu").json()["escritorio"]["id"]
    with nova_sessao() as db:
        e = db.get(Escritorio, esc)
        db.expunge(e)
        return e


def test_cadastro_comeca_30_dias_de_teste(servidor, cliente):
    assert cliente.post("/api/auth/sair").status_code == 204
    assert cliente.get("/api/auth/eu").json()["teste_dias"] == 30
    r = cliente.post("/api/auth/cadastrar", json={"nome": "Ana", "email": "ana@empresa.com.br",
                                                  "senha": "Senha-Forte-123", "tipo": "empresa"})
    assert r.status_code == 201, r.text
    e = _escritorio(cliente)
    assert e.situacao == "teste" and e.tipo == "empresa"
    assert e.teste_ate == escritorios.hoje() + timedelta(days=29)
    uso = cliente.get("/api/uso").json()
    assert uso["teste"] is None  # sem os limites do teste antigo
    assert uso["periodo_teste"] == {"ate": e.teste_ate.isoformat(), "dias_restantes": 30}


def test_teste_completo_libera_tudo(servidor, cliente, sefin):
    assert _escritorio(cliente).situacao == "teste"
    e, s = _pronta(cliente)
    for _ in range(3):  # o teste limitado permitia 1 emissão
        n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
        assert n["situacao"] == "autorizada", n
    r = cliente.get(f"/api/emissor/notas/{n['id']}/xml")
    assert r.status_code == 200  # XML liberado


def test_fim_do_teste_fecha_o_acesso(servidor, cliente):
    esc = _escritorio(cliente).id
    with nova_sessao() as db:
        db.get(Escritorio, esc).teste_ate = escritorios.hoje() - timedelta(days=1)
        db.commit()
    assert cliente.get("/api/uso").status_code == 401  # a sessão cai
    r = cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE})
    assert r.status_code == 401 and "período de teste" in r.json()["detail"], r.text


def test_sem_configuracao_a_conta_nasce_ativa(cliente):
    e = _escritorio(cliente)
    assert e.situacao == "ativo" and e.teste_ate is None
    assert cliente.get("/api/uso").json()["periodo_teste"] is None


def test_limite_de_cadastros_por_ip(servidor, app_teste):
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as c:
        for i in range(3):
            c.cookies.clear()
            assert c.post("/api/auth/cadastrar", json={"nome": f"N{i}", "email": f"n{i}@x.com.br",
                                                       "senha": "Senha-Forte-123"}).status_code == 201
        c.cookies.clear()
        r = c.post("/api/auth/cadastrar", json={"nome": "N4", "email": "n4@x.com.br", "senha": "Senha-Forte-123"})
        assert r.status_code == 429
