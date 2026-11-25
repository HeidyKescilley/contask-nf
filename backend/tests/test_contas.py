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
    # Sem a sessão da administração, ninguém entra no painel
    assert cliente.get("/api/admin/escritorios").status_code == 401
    assert cliente.get("/api/auth/eu").json()["usuario"]["admin_sistema"] is False
    # O papel só é concedido pelo servidor
    from tests.conftest import entrar_admin; entrar_admin(cliente)
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
    assert cliente.get("/api/admin/escritorios").status_code == 401


def test_administracao_separada_do_sistema(cliente):
    """Login, cookie e sessão próprios: a sessão do sistema não abre a administração, e vice-versa."""
    from app.core import autenticacao as auth
    from app.tools import usuarios
    # Quem não é administrador recebe a mesma resposta de senha errada
    r = cliente.post("/api/admin/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha incorretos."
    usuarios.main(["admin", "teste@contask.local"])
    # Logado no sistema, mas sem entrar na administração: o painel não abre
    assert cliente.get("/api/auth/eu").json()["usuario"] is not None
    assert cliente.get("/api/admin/auth/eu").json()["usuario"] is None
    assert cliente.get("/api/admin/escritorios").status_code == 401
    r = cliente.post("/api/admin/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE})
    assert r.status_code == 200 and r.json()["usuario"]["email"] == "teste@contask.local"
    assert cliente.cookies.get(auth.COOKIE_ADMIN) and cliente.get("/api/admin/escritorios").status_code == 200
    # Só com o cookie da administração: o sistema (empresas, notas) não abre
    adm = cliente.cookies.get(auth.COOKIE_ADMIN)
    cliente.cookies.clear()
    cliente.cookies.set(auth.COOKIE_ADMIN, adm)
    assert cliente.get("/api/empresas").status_code == 401
    assert cliente.get("/api/admin/escritorios").status_code == 200
    # O token da administração no cookie do sistema também não vale
    cliente.cookies.set(auth.COOKIE, adm)
    assert cliente.get("/api/auth/eu").json()["usuario"] is None
    # Sair da administração não derruba o sistema
    cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE}).status_code == 200
    assert cliente.post("/api/admin/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE}).status_code == 200
    assert cliente.post("/api/admin/auth/sair").status_code == 204
    assert cliente.get("/api/admin/escritorios").status_code == 401
    assert cliente.get("/api/auth/eu").json()["usuario"] is not None


def test_usuarios_so_da_administracao(app_teste, cliente):
    """A administração cria usuários próprios: sem escritório, trocam a senha no primeiro login
    e nunca entram no sistema."""
    from app.core import autenticacao as auth
    from tests.conftest import entrar_admin
    entrar_admin(cliente)
    r = cliente.post("/api/admin/administradores", json={"email": "Gestao@Contask.local", "nome": "Gestão"})
    assert r.status_code == 201, r.text
    novo, senha = r.json()["usuario"], r.json()["senha_inicial"]
    assert novo["so_administracao"] and novo["escritorio_id"] is None and novo["trocar_senha"]
    assert cliente.post("/api/admin/administradores", json={"email": "gestao@contask.local"}).status_code == 409
    lista = cliente.get("/api/admin/administradores").json()
    assert {u["email"] for u in lista} == {"teste@contask.local", "gestao@contask.local"}
    assert next(u for u in lista if u["email"] == "teste@contask.local")["escritorio"]
    # Não aparece como usuário de nenhum escritório nos Clientes
    assert all(u["email"] != "gestao@contask.local" for e in cliente.get("/api/admin/escritorios").json() for u in e["usuarios"])

    g = TestClient(app_teste, base_url="http://127.0.0.1:8765")
    # O sistema recusa (acesso só da administração), sem criar sessão
    r = g.post("/api/auth/entrar", json={"email": "gestao@contask.local", "senha": senha})
    assert r.status_code == 401 and "/admin" in r.json()["detail"] and not g.cookies.get(auth.COOKIE)
    # Na administração entra, mas só troca a senha até trocar
    r = g.post("/api/admin/auth/entrar", json={"email": "gestao@contask.local", "senha": senha})
    assert r.status_code == 200 and r.json()["usuario"]["trocar_senha"]
    r = g.get("/api/admin/escritorios")
    assert r.status_code == 403 and r.json()["detail"].startswith("Troque a senha")
    assert g.post("/api/admin/auth/senha", json={"senha_atual": "errada", "senha_nova": "Nova-Senha-123"}).status_code == 400
    r = g.post("/api/admin/auth/senha", json={"senha_atual": senha, "senha_nova": "Nova-Senha-123"})
    assert r.status_code == 200 and not r.json()["usuario"]["trocar_senha"]
    assert g.get("/api/admin/escritorios").status_code == 200
    # Mesmo com o token da administração no cookie do sistema, o sistema não abre
    g.cookies.set(auth.COOKIE, g.cookies.get(auth.COOKIE_ADMIN))
    assert g.get("/api/auth/eu").json()["usuario"] is None and g.get("/api/empresas").status_code == 401
    assert g.post("/api/auth/entrar", json={"email": "gestao@contask.local", "senha": "Nova-Senha-123"}).status_code == 401

    # Só da administração: não perde o papel, é desativado (e sai na hora)
    assert cliente.delete(f"/api/admin/administradores/{novo['id']}").status_code == 409
    assert cliente.put(f"/api/admin/usuarios/{novo['id']}/ativo", json={"ativo": False}).status_code == 200
    assert g.get("/api/admin/escritorios").status_code == 401
    # Ninguém tira o próprio acesso
    eu = next(u for u in lista if u["email"] == "teste@contask.local")
    assert cliente.delete(f"/api/admin/administradores/{eu['id']}").status_code == 409


def test_tirar_administracao_de_quem_usa_o_sistema(app_teste, cliente):
    """Quem também usa o sistema perde só a administração: a sessão de lá cai, o sistema continua."""
    from app.core.db import nova_sessao
    from app.models import Usuario
    from tests.conftest import entrar_admin
    entrar_admin(cliente)
    r = cliente.post("/api/admin/administradores", json={"email": "gestao@contask.local"})
    senha = r.json()["senha_inicial"]
    g = TestClient(app_teste, base_url="http://127.0.0.1:8765")
    g.post("/api/admin/auth/entrar", json={"email": "gestao@contask.local", "senha": senha})
    g.post("/api/admin/auth/senha", json={"senha_atual": senha, "senha_nova": "Nova-Senha-123"})
    teste = next(u for u in g.get("/api/admin/administradores").json() if u["email"] == "teste@contask.local")
    r = g.delete(f"/api/admin/administradores/{teste['id']}")
    assert r.status_code == 200 and not r.json()["admin_sistema"]
    assert cliente.get("/api/admin/escritorios").status_code == 401  # a sessão da administração caiu
    assert cliente.get("/api/empresas").status_code == 200  # o sistema continua
    with nova_sessao() as db:
        assert not db.get(Usuario, teste["id"]).admin_sistema


def _admin_com_escritorio(cliente, **plano):
    from app.tools import usuarios
    from tests.conftest import entrar_admin; entrar_admin(cliente)
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
