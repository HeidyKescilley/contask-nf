"""Login, domínio público, chave-mestra e limite mensal de XMLs."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import autenticacao as auth
from app.core.db import nova_sessao
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob, SyncEstado
from tests.adn_simulado import ADNSimulado, chave_fake, nfse_xml
from tests.certs import criar_pfx, dv_cnpj

DOMINIO = "escritorio.contasknf.com.br"
SENHA = "Senha-Forte-123"


@pytest.fixture()
def app_login(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTASK_HOSTS", DOMINIO)
    monkeypatch.setenv("CONTASK_COOKIE_SECURE", "true")
    auth.limitador.limpar(*list(auth.limitador._erros))
    yield


@pytest.fixture()
def web(app_login, app_teste):
    with TestClient(app_teste, base_url=f"https://{DOMINIO}") as c:
        with nova_sessao() as db:
            auth.criar_usuario(db, "Ana@Escritorio.com", "Ana", SENHA, trocar_senha=False)
            db.commit()
        yield c


def entrar(c, email="ana@escritorio.com", senha=SENHA):
    return c.post("/api/auth/entrar", json={"email": email, "senha": senha})


def test_api_exige_login_e_libera_depois(web):
    assert web.get("/api/empresas").status_code == 401
    assert web.get("/api/ping").json() == {"ok": True}
    assert web.get("/api/auth/eu").json()["usuario"] is None
    r = entrar(web, email="  ANA@escritorio.com ")
    assert r.status_code == 200 and r.json()["usuario"]["nome"] == "Ana"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert SENHA not in r.text
    assert web.get("/api/empresas").status_code == 200
    assert web.get("/api/auth/eu").json()["usuario"]["email"] == "ana@escritorio.com"
    assert web.get("/api/empresas").headers["cache-control"] == "no-store"
    assert web.post("/api/auth/sair").status_code == 204
    assert web.get("/api/empresas").status_code == 401


def test_frontend_e_publico_mas_api_nao(web):
    assert web.get("/dashboard").status_code in (200, 503)  # SPA (sem build nos testes)
    saude = web.get("/api/saude")
    assert saude.status_code == 200 and "empresas" not in saude.json()


def test_senha_errada_e_bloqueio(web):
    for _ in range(5):
        r = entrar(web, senha="errada")
        assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha incorretos."
    r = entrar(web)  # mesmo com a senha certa, fica bloqueado
    assert r.status_code == 401 and "Muitas tentativas" in r.json()["detail"]
    assert entrar(web, email="naoexiste@x.com", senha="x").status_code == 401


def test_sessao_vencida_nao_vale(web):
    entrar(web)
    with nova_sessao() as db:
        from app.models import SessaoUsuario
        for s in db.query(SessaoUsuario):
            s.expira_em = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert web.get("/api/empresas").status_code == 401


def test_troca_de_senha_obrigatoria(web):
    with nova_sessao() as db:
        auth.criar_usuario(db, "novo@escritorio.com", "Novo", "Inicial-12345", trocar_senha=True)
        db.commit()
    assert entrar(web, "novo@escritorio.com", "Inicial-12345").json()["usuario"]["trocar_senha"] is True
    r = web.get("/api/empresas")
    assert r.status_code == 403 and "Troque a senha" in r.json()["detail"]
    assert web.post("/api/auth/senha", json={"senha_atual": "x", "senha_nova": "Nova-Senha-999"}).status_code == 400
    assert web.post("/api/auth/senha", json={"senha_atual": "Inicial-12345", "senha_nova": "fraca"}).status_code == 400
    r = web.post("/api/auth/senha", json={"senha_atual": "Inicial-12345", "senha_nova": "Nova-Senha-999"})
    assert r.status_code == 200 and r.json()["usuario"]["trocar_senha"] is False
    assert web.get("/api/empresas").status_code == 200


def test_dominio_e_origem(web):
    entrar(web)
    assert web.get("/api/empresas", headers={"host": "outro.com"}).status_code == 400
    assert web.post("/api/auth/sair", headers={"origin": "https://malicioso.com"}).status_code == 403
    assert web.get("/api/empresas", headers={"origin": f"https://{DOMINIO}"}).status_code == 200
    assert "max-age" in web.get("/api/ping").headers["strict-transport-security"]


def test_sem_dominio_fora_do_localhost_nao_sobe(tmp_path, monkeypatch, app_teste):
    monkeypatch.setenv("CONTASK_HOST", "0.0.0.0")
    monkeypatch.setenv("CONTASK_HOSTS", "")
    from app.core import config as cfgmod
    cfgmod.config.cache_clear()
    with pytest.raises(RuntimeError, match="CONTASK_HOSTS"):
        with TestClient(app_teste):
            pass


def test_sem_chave_mestra_nao_sobe(app_teste, monkeypatch):
    monkeypatch.setenv("CONTASK_CHAVE_MESTRA", "")
    from app.core import config as cfgmod, cripto
    cfgmod.config.cache_clear()
    cripto.definir_chave_para_testes(None)
    with pytest.raises(RuntimeError, match="CONTASK_CHAVE_MESTRA"):
        with TestClient(app_teste):
            pass


def test_ferramenta_de_usuarios(app_teste, capsys):
    from app.tools import usuarios
    with TestClient(app_teste):
        usuarios.main(["criar", "joao@escritorio.com", "João"])
        saida = capsys.readouterr().out
        senha = saida.strip().rsplit(" ", 1)[-1]
        with nova_sessao() as db:
            u, _ = auth.entrar(db, "joao@escritorio.com", senha, "1.1.1.1")
            assert u.trocar_senha
        usuarios.main(["desativar", "joao@escritorio.com"])
        with nova_sessao() as db, pytest.raises(auth.ErroLogin):
            auth.entrar(db, "joao@escritorio.com", senha, "1.1.1.2")


# --- limite mensal de XMLs -----------------------------------------------------

CONTAB = dv_cnpj("112223330001")
EMP = dv_cnpj("114447770001")


def _preparar(cliente, n_notas: int) -> tuple[int, ADNSimulado]:
    cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": "S3nh@-Teste!"},
                 files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    eid = cliente.post("/api/empresas", data={"cnpj": EMP, "razao_social": "Empresa",
                                              "modo_certificado": "contabilidade"}).json()["empresa"]["id"]
    adn = ADNSimulado()
    for i in range(1, n_notas + 1):
        ch = chave_fake(i, EMP)
        adn.adicionar(EMP, "NFSE", ch, nfse_xml(ch, prest=EMP, toma="33000167000101"))
    return eid, adn


def _rodar(adn, empresa_id: int, tipo: str | None = None) -> BuscaJob:
    with nova_sessao() as db:
        if tipo:
            db.add(BuscaJob(empresa_id=empresa_id, tipo=tipo, status="fila"))
            db.commit()
        jid = db.query(BuscaJob.id).filter(BuscaJob.empresa_id == empresa_id, BuscaJob.status == "fila").scalar()
    executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))
    with nova_sessao() as db:
        return db.get(BuscaJob, jid)


def test_carga_inicial_nao_conta_e_limite_bloqueia_incremental(cliente, monkeypatch):
    from app.core import config as cfgmod
    monkeypatch.setenv("CONTASK_LIMITE_XMLS_MES", "60")
    cfgmod.config.cache_clear()
    eid, adn = _preparar(cliente, 120)
    j = _rodar(adn, eid)  # inicial: 120 documentos, não conta
    assert j.status == "concluido" and j.docs_recebidos == 120
    u = cliente.get("/api/uso").json()
    assert u["usados"] == 0 and u["limite"] == 60 and u["situacao"] == "ok"

    for i in range(121, 221):  # 100 notas novas
        ch = chave_fake(i, EMP)
        adn.adicionar(EMP, "NFSE", ch, nfse_xml(ch, prest=EMP, toma="33000167000101"))
    j = _rodar(adn, eid, "incremental")
    # Para na primeira página depois de atingir o limite (lotes de 50)
    assert j.status == "erro" and "Limite mensal" in j.mensagem and j.docs_recebidos == 100
    with nova_sessao() as db:
        assert db.get(SyncEstado, eid).situacao == "limite_mes"
    u = cliente.get("/api/uso").json()
    assert u["usados"] >= 60 and u["situacao"] == "atingido"

    j = _rodar(adn, eid, "incremental")  # nova tentativa no mesmo mês: nem chama o ADN
    assert j.status == "erro" and j.docs_recebidos == 0
    with nova_sessao() as db:
        assert db.get(SyncEstado, eid).situacao == "limite_mes"


def test_empresa_nunca_buscada_conta_como_historico(cliente, monkeypatch):
    from app.core import config as cfgmod
    monkeypatch.setenv("CONTASK_LIMITE_XMLS_MES", "10")
    cfgmod.config.cache_clear()
    eid, adn = _preparar(cliente, 30)
    with nova_sessao() as db:  # a inicial falhou antes de terminar (ex.: sem procuração) e virou incremental
        db.query(BuscaJob).filter(BuscaJob.empresa_id == eid).update({"status": "erro"})
        db.commit()
    j = _rodar(adn, eid, "incremental")
    assert j.tipo == "inicial" and j.status == "concluido" and j.docs_recebidos == 30
    assert cliente.get("/api/uso").json()["usados"] == 0


def test_sem_limite(cliente):
    assert cliente.get("/api/uso").json()["situacao"] == "sem_limite"


# --- teste grátis (1 empresa, 5 XMLs) ------------------------------------------

@pytest.fixture()
def modo_teste(monkeypatch):
    from app.core import config as cfgmod
    monkeypatch.setenv("CONTASK_TESTE", "true")
    cfgmod.config.cache_clear()
    yield
    cfgmod.config.cache_clear()


def test_teste_baixa_so_5_xmls_e_continua_depois_de_liberar(cliente, modo_teste, monkeypatch):
    eid, adn = _preparar(cliente, 120)
    with nova_sessao() as db:  # a contabilidade não foi agendada; só a empresa escolhida
        tipos = {(j.empresa_id, j.tipo) for j in db.query(BuscaJob)}
    assert tipos == {(eid, "inicial")}
    j = _rodar(adn, eid)
    assert j.status == "erro" and "Teste grátis concluído" in j.mensagem and j.docs_recebidos == 5
    with nova_sessao() as db:
        from app.models import DocumentoDfe, Nota
        assert db.query(DocumentoDfe).count() == 5 and db.query(Nota).count() == 5
        sync = db.get(SyncEstado, eid)
        assert sync.situacao == "limite_teste" and sync.ultima_busca_em is None
        nsu_salvo = sync.ultimo_nsu
    u = cliente.get("/api/uso").json()
    assert u["situacao"] == "teste" and u["usados"] == 5 and u["teste"]["concluido"] is True

    j = _rodar(adn, eid, "incremental")  # nova tentativa: nem chama o ADN
    assert j.status == "erro" and j.docs_recebidos == 0

    # Assinou: desliga o teste; a busca continua do NSU salvo e o histórico não conta no limite do mês
    from app.core import config as cfgmod
    monkeypatch.setenv("CONTASK_TESTE", "false")
    monkeypatch.setenv("CONTASK_LIMITE_XMLS_MES", "10")
    cfgmod.config.cache_clear()
    j = _rodar(adn, eid, "incremental")
    assert j.tipo == "inicial" and j.status == "concluido" and j.docs_recebidos == 115
    assert nsu_salvo > 0
    with nova_sessao() as db:
        from app.models import Nota
        assert db.query(Nota).count() == 120
    assert cliente.get("/api/uso").json()["usados"] == 0


def test_teste_aceita_uma_empresa(cliente, modo_teste):
    _preparar(cliente, 1)
    r = cliente.post("/api/empresas", data={"cnpj": dv_cnpj("223334440001"), "razao_social": "Outra",
                                            "modo_certificado": "contabilidade"})
    assert r.status_code == 403 and "teste grátis" in r.json()["detail"]
    r = cliente.post("/api/importacao/empresas", json={"linhas": [{"cnpj": dv_cnpj("223334440001")}]})
    assert r.status_code == 403
    # Reenviar a mesma empresa que já existe não conta como nova
    r = cliente.post("/api/importacao/empresas", json={"linhas": [{"cnpj": EMP}]})
    assert r.status_code == 200


def test_teste_nao_busca_a_contabilidade(cliente, modo_teste):
    eid, adn = _preparar(cliente, 3)
    with nova_sessao() as db:
        from app.models import Empresa
        contab = db.query(Empresa).filter(Empresa.is_contabilidade).one()
        db.add(BuscaJob(empresa_id=contab.id, tipo="incremental", status="fila"))
        db.commit()
    j = _rodar(adn, contab.id)
    assert j.status == "cancelado" and "contabilidade" in j.mensagem and j.docs_recebidos == 0
