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


def test_painel_de_administracao(cliente, capsys):
    from app.tools import usuarios
    # Usuário comum não entra no painel
    assert cliente.get("/api/admin/escritorios").status_code == 403
    assert cliente.get("/api/auth/eu").json()["usuario"]["admin_sistema"] is False
    # O papel só é concedido pelo servidor
    usuarios.main(["admin", "teste@contask.local"])
    assert cliente.get("/api/auth/eu").json()["usuario"]["admin_sistema"] is True
    r = cliente.post("/api/admin/escritorios", json={"nome": "Contábil Silva", "email": "ana@silva.com", "nome_usuario": "Ana"})
    assert r.status_code == 201, r.text
    senha, ana = r.json()["senha_inicial"], r.json()["usuario"]
    assert ana["trocar_senha"] and len(senha) >= 10
    r = cliente.post(f"/api/admin/escritorios/{ana['escritorio_id']}/usuarios", json={"email": "bia@silva.com", "nome": "Bia"})
    assert r.status_code == 201
    assert cliente.post("/api/admin/escritorios", json={"nome": "Outro", "email": "ana@silva.com"}).status_code == 409
    lista = cliente.get("/api/admin/escritorios").json()
    silva = next(e for e in lista if e["nome"] == "Contábil Silva")
    assert {u["email"] for u in silva["usuarios"]} == {"ana@silva.com", "bia@silva.com"}
    # Nova senha e desativar
    nova = cliente.post(f"/api/admin/usuarios/{ana['id']}/senha").json()["senha_inicial"]
    assert nova != senha
    assert cliente.put(f"/api/admin/usuarios/{ana['id']}/ativo", json={"ativo": False}).json()["ativo"] is False
    eu = cliente.get("/api/auth/eu").json()["usuario"]["id"]
    assert cliente.put(f"/api/admin/usuarios/{eu}/ativo", json={"ativo": False}).status_code == 409
    # O escritório novo não enxerga as empresas do admin, e vice-versa (isolamento continua pelo login)
    usuarios.main(["admin", "teste@contask.local", "--remover"])
    assert cliente.get("/api/admin/escritorios").status_code == 403


def _admin_com_escritorio(cliente, **plano):
    from app.tools import usuarios
    usuarios.main(["admin", "teste@contask.local"])
    r = cliente.post("/api/admin/escritorios", json={"nome": "Contábil Silva", "email": "ana@silva.com", "nome_usuario": "Ana", **plano})
    assert r.status_code == 201, r.text
    return r.json()


def _entrar_como(app_teste, email, senha):
    c = TestClient(app_teste, base_url="http://127.0.0.1:8765")
    return c, c.post("/api/auth/entrar", json={"email": email, "senha": senha})


def test_suspender_bloqueia_acesso_e_reativar_libera(app_teste, cliente):
    from app.core import autenticacao as auth
    from app.core.db import nova_sessao
    from sqlalchemy import select
    from app.models import Usuario
    criado = _admin_com_escritorio(cliente)
    esc = criado["usuario"]["escritorio_id"]
    with nova_sessao() as db:  # Ana já trocou a senha
        u = db.scalar(select(Usuario).where(Usuario.email == "ana@silva.com"))
        u.senha_hash, u.trocar_senha = auth.gerar_hash(SENHA_TESTE), False
        db.commit()
    ana, r = _entrar_como(app_teste, "ana@silva.com", SENHA_TESTE)
    assert r.status_code == 200 and ana.get("/api/empresas").status_code == 200
    corpo = {"nome": "Contábil Silva", "situacao": "suspenso"}
    r = cliente.put(f"/api/admin/escritorios/{esc}", json=corpo)
    assert r.status_code == 200 and r.json()["bloqueio"]
    assert ana.get("/api/empresas").status_code == 401  # sessão deixa de valer
    _, r = _entrar_como(app_teste, "ana@silva.com", SENHA_TESTE)
    assert r.status_code == 401 and "suspenso" in r.json()["detail"]
    cliente.put(f"/api/admin/escritorios/{esc}", json={**corpo, "situacao": "ativo"})
    assert ana.get("/api/empresas").status_code == 200  # volta sem novo login
    hist = cliente.get(f"/api/admin/escritorios/{esc}/historico").json()
    assert [h["tipo"] for h in hist][:2] == ["situacao", "situacao"] and hist[-1]["tipo"] == "criado"
    # O escritório do administrador não pode ser suspenso
    eu = cliente.get("/api/auth/eu").json()["escritorio"]["id"]
    assert cliente.put(f"/api/admin/escritorios/{eu}", json={"nome": "X Y", "situacao": "suspenso"}).status_code == 409


def test_teste_vencido_bloqueia_e_plano_por_escritorio(app_teste, cliente):
    from datetime import timedelta
    from app.core import escritorios, uso
    from app.core.db import nova_sessao
    criado = _admin_com_escritorio(cliente, situacao="teste", teste_ate=str(escritorios.hoje() + timedelta(days=7)),
                                   limite_xmls_mes=500)
    esc = criado["usuario"]["escritorio_id"]
    with nova_sessao() as db:
        assert escritorios.em_teste(db, esc) and not escritorios.bloqueado(db, esc)
        assert escritorios.limite_xmls(db, esc) == 500
        assert uso.resumo(db, esc)["situacao"] == "teste"
    ontem = str(escritorios.hoje() - timedelta(days=1))
    r = cliente.put(f"/api/admin/escritorios/{esc}", json={"nome": "Contábil Silva", "situacao": "teste", "teste_ate": ontem})
    assert "teste" in r.json()["bloqueio"]
    with nova_sessao() as db:
        assert esc in escritorios.ids_bloqueados(db)


def test_pagamento_empurra_vencimento(cliente):
    criado = _admin_com_escritorio(cliente, mensalidade="79.90", dia_vencimento=31, proximo_vencimento="2026-10-31")
    esc = criado["usuario"]["escritorio_id"]
    lista = {e["id"]: e for e in cliente.get("/api/admin/escritorios").json()}
    assert lista[esc]["dias_atraso"] > 0 and lista[esc]["mensalidade"] == 79.9
    r = cliente.post(f"/api/admin/escritorios/{esc}/pagamento", json={"observacao": "Pix"}).json()
    assert r["proximo_vencimento"] == "2026-11-30"  # 31 em mês de 30 dias
    r = cliente.post(f"/api/admin/escritorios/{esc}/pagamento", json={}).json()
    assert r["proximo_vencimento"] == "2026-12-31"
    pag = [h for h in cliente.get(f"/api/admin/escritorios/{esc}/historico").json() if h["tipo"] == "pagamento"]
    assert len(pag) == 2 and pag[-1]["valor"] == 79.9 and "Pix" in pag[-1]["descricao"]
