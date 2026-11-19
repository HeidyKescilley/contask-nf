"""Monitoramento do uso: coleta (eventos, gravação, pesquisa, suporte) e o painel do administrador."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import nova_sessao
from app.models import Gravacao, UsoEvento, Usuario

SESSAO = "aba-teste-0001"


def _lote(*eventos, sessao=SESSAO):
    return {"sessao": sessao, "eventos": list(eventos)}


def _cliente_ana(app_teste, cliente):
    """teste@contask.local vira admin; Ana (outro escritório, usuária comum) entra num cliente próprio."""
    from app.tools import usuarios
    usuarios.main(["admin", "teste@contask.local"])
    r = cliente.post("/api/admin/escritorios", json={"nome": "Contábil Silva", "email": "ana@silva.com", "nome_usuario": "Ana"})
    assert r.status_code == 201, r.text
    senha = r.json()["senha_inicial"]
    with nova_sessao() as db:
        u = db.scalar(select(Usuario).where(Usuario.email == "ana@silva.com"))
        u.trocar_senha = False
        db.commit()
    ana = TestClient(app_teste, base_url="http://127.0.0.1:8765")
    assert ana.post("/api/auth/entrar", json={"email": "ana@silva.com", "senha": senha}).status_code == 200
    return ana


def test_eventos_normalizados_e_limpos(cliente):
    r = cliente.post("/api/uso/eventos", json=_lote(
        {"tipo": "pagina", "nome": "/empresas/123?aba=2"},
        {"tipo": "clique", "nome": "/empresas/123", "dados": {"x": 1.7, "y": 300, "w": 1280, "h": 2000, "alvo": "Salvar",
                                                             "cnpj": "11222333000181"}},
        {"tipo": "tempo", "nome": "/empresas/123", "dados": {"s": 15}},
        {"tipo": "hackear", "nome": "x"},
    ))
    assert r.status_code == 204
    with nova_sessao() as db:
        evs = list(db.scalars(select(UsoEvento).where(UsoEvento.sessao == SESSAO).order_by(UsoEvento.id)))
    assert [e.tipo for e in evs] == ["pagina", "clique", "tempo"]
    assert evs[0].nome == "/empresas/:id"
    assert evs[1].dados["x"] == 1 and "cnpj" not in evs[1].dados  # campo fora do esperado é descartado
    assert cliente.post("/api/uso/eventos", json=_lote(sessao="curta")).status_code == 422


def test_acoes_gravadas_pelo_servidor(cliente):
    cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": "Senha-Forte-123"})
    from tests.test_empresas import _contabilidade
    assert _contabilidade(cliente).status_code == 200
    with nova_sessao() as db:
        nomes = [e.nome for e in db.scalars(select(UsoEvento).where(UsoEvento.tipo.in_(("login", "acao"))))]
    assert "login" in nomes and "contabilidade_cadastrada" in nomes


def test_gravacao_em_trechos(cliente):
    for i in range(3):
        r = cliente.post("/api/uso/gravacao", json={"sessao": SESSAO, "pagina": f"/empresas/{i}",
                                                    "eventos": [{"type": 3, "timestamp": i, "data": {}}]})
        assert r.status_code == 204
    from app.api.uso import ler_gravacao
    with nova_sessao() as db:
        g = db.scalar(select(Gravacao).where(Gravacao.sessao == SESSAO))
        assert [e["timestamp"] for e in ler_gravacao(g)] == [0, 1, 2]
        assert g.paginas == ["/empresas/:id"] and g.tamanho > 0


def test_pesquisa_so_depois_de_uso(cliente):
    assert cliente.get("/api/uso/pesquisa").json()["mostrar"] is False  # conta nova
    with nova_sessao() as db:
        u = db.scalar(select(Usuario).where(Usuario.email == "teste@contask.local"))
        u.criado_em = datetime.now(timezone.utc) - timedelta(days=20)
        for d in (1, 3, 5):
            db.add(UsoEvento(escritorio_id=u.escritorio_id, usuario_id=u.id, sessao=SESSAO, tipo="pagina", nome="/",
                             momento=datetime.now(timezone.utc) - timedelta(days=d)))
        db.commit()
    assert cliente.get("/api/uso/pesquisa").json()["mostrar"] is True
    assert cliente.post("/api/uso/pesquisa", json={"adiada": True}).status_code == 201
    assert cliente.get("/api/uso/pesquisa").json()["mostrar"] is False
    assert cliente.post("/api/uso/pesquisa", json={}).status_code == 422


def test_painel_so_para_admin_e_sem_o_proprio_admin(app_teste, cliente):
    assert cliente.get("/api/admin/monitoramento/resumo").status_code == 403
    cliente.post("/api/uso/eventos", json=_lote({"tipo": "pagina", "nome": "/dashboard"}))  # vira admin: fica de fora
    ana = _cliente_ana(app_teste, cliente)
    assert ana.get("/api/admin/monitoramento/resumo").status_code == 403
    ana.post("/api/uso/eventos", json=_lote(
        {"tipo": "pagina", "nome": "/dashboard"}, {"tipo": "tempo", "nome": "/dashboard", "dados": {"s": 120}},
        {"tipo": "pagina", "nome": "/exportacoes"},
        {"tipo": "clique", "nome": "/exportacoes", "dados": {"x": 0.5, "y": 200, "w": 1280, "h": 900, "alvo": "Texto", "morto": True}},
        {"tipo": "rolagem", "nome": "/exportacoes", "dados": {"p": 60}},
        {"tipo": "erro", "nome": "api", "dados": {"msg": "Erro 500", "rota": "/exportacoes"}},
        sessao="aba-ana-00001"))
    ana.post("/api/uso/gravacao", json={"sessao": "aba-ana-00001", "pagina": "/dashboard", "eventos": [{"type": 4, "timestamp": 1}]})
    assert ana.post("/api/uso/pesquisa", json={"decepcao": "muito", "horas": 10, "nps": 9, "comentario": "Ótimo"}).status_code == 201
    assert ana.post("/api/uso/suporte", json={"assunto": "buscas", "mensagem": "A busca não termina.", "pagina": "/empresas/4"}).status_code == 201
    assert ana.post("/api/uso/suporte", json={"assunto": "xyz", "mensagem": "Oi oi oi"}).status_code == 422

    r = cliente.get("/api/admin/monitoramento/resumo", params={"dias": 30})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ativacao"]["usuarios"] == 1  # só a Ana; o admin fica fora
    assert [x["nome"] for x in d["ativacao"]["escritorios"]] == ["Contábil Silva"]
    linha = d["uso"]["por_usuario"][0]
    assert linha["nome"] == "Ana" and linha["funcoes"]["dashboard"] == 1 and linha["funcoes"]["exportacao"] == 1
    assert "Emissor de notas" in linha["nao_usa"]
    assert d["frequencia"]["sessao_media_min"] == 2.0
    assert d["retencao"]["usaram"] == 1
    assert d["pesquisa"]["pct_muito"] == 100 and d["pesquisa"]["nps"] == 100
    assert d["erros"]["erros_tela"][0]["mensagem"] == "Erro 500"
    assert d["suporte"]["abertos"] == 1 and d["suporte"]["por_assunto"][0]["assunto"] == "Busca de notas"

    x = cliente.get("/api/admin/monitoramento/experiencia", params={"rota": "/exportacoes"}).json()
    assert x["transicoes"][0] == {"de": "/dashboard", "para": "/exportacoes", "vezes": 1}
    assert x["abandono"][0]["rota"] == "/exportacoes"
    assert x["cliques_mortos"][0]["alvo"] == "Texto"
    assert x["rota"]["rolagem"][6] == {"ate": 60, "pct": 100.0} and x["rota"]["rolagem"][7]["pct"] == 0

    gs = cliente.get("/api/admin/monitoramento/gravacoes").json()
    assert len(gs) == 1 and gs[0]["usuario"] == "Ana"
    assert cliente.get(f"/api/admin/monitoramento/gravacoes/{gs[0]['id']}").json()["eventos"] == [{"type": 4, "timestamp": 1}]
    pid = d["suporte"]["pedidos"][0]["id"]
    assert cliente.put(f"/api/admin/monitoramento/suporte/{pid}").json()["situacao"] == "resolvido"


def test_gravacao_do_admin_nao_e_guardada(cliente):
    from app.tools import usuarios
    usuarios.main(["admin", "teste@contask.local"])
    cliente.post("/api/uso/gravacao", json={"sessao": SESSAO, "pagina": "/", "eventos": [{"type": 4}]})
    with nova_sessao() as db:
        assert db.scalar(select(Gravacao)) is None


def test_limpeza_de_gravacoes_antigas(cliente):
    cliente.post("/api/uso/gravacao", json={"sessao": SESSAO, "pagina": "/", "eventos": [{"type": 4}]})
    from app.api.uso import limpar_antigos
    from app.core.config import config
    with nova_sessao() as db:
        g = db.scalar(select(Gravacao))
        arq = config().dados_dir / g.arquivo
        assert arq.is_file()
        g.iniciado_em = datetime.now(timezone.utc) - timedelta(days=31)
        db.commit()
        assert limpar_antigos(db) == 1
    assert not arq.exists()
