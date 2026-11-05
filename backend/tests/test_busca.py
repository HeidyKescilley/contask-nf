"""Motor de busca contra o ADN simulado."""
import itertools
import time

import pytest
from sqlalchemy import func, select

from app.core.db import nova_sessao
from app.fiscal.status import EventoStatus, calcular_status
from app.jobs.fila import Gerenciador, enfileirar
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob, DocumentoDfe, EventoNota, Nota, SyncEstado
from tests.adn_simulado import ADNSimulado, FalhaSimulada, chave_fake
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
C1, C2, C3 = dv_cnpj("114447770001"), dv_cnpj("223334440001"), dv_cnpj("556667770001")


@pytest.fixture()
def base(cliente):
    """Contabilidade + 3 empresas: C1 e C2 pelo certificado da contabilidade, C3 com certificado próprio."""
    r = cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": SENHA},
                     files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    assert r.status_code == 200, r.text
    ids = {}
    for cnpj in (C1, C2):
        r = cliente.post("/api/empresas", data={"cnpj": cnpj, "razao_social": f"Empresa {cnpj}", "modo_certificado": "contabilidade"})
        ids[cnpj] = r.json()["empresa"]["id"]
    r = cliente.post("/api/empresas", data={"cnpj": C3, "razao_social": "Empresa 3", "modo_certificado": "proprio", "senha": SENHA},
                     files={"arquivo": ("p.pfx", criar_pfx("EMPRESA 3", cnpj=C3), "application/x-pkcs12")})
    ids[C3] = r.json()["empresa"]["id"]
    ids["contab"] = cliente.get("/api/contabilidade").json()["id"]
    return ids


def _job(empresa_id: int) -> int:
    with nova_sessao() as db:
        return db.scalar(select(BuscaJob.id).where(BuscaJob.empresa_id == empresa_id, BuscaJob.status == "fila"))


def _rodar(adn: ADNSimulado, empresa_id: int, job_id: int | None = None) -> str:
    return executar_job(job_id or _job(empresa_id), nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))


def _contagens(empresa_id: int) -> dict:
    with nova_sessao() as db:
        return {
            "docs": db.scalar(select(func.count()).select_from(DocumentoDfe).where(DocumentoDfe.empresa_id == empresa_id)),
            "notas": db.scalar(select(func.count()).select_from(Nota).where(Nota.empresa_id == empresa_id)),
            "eventos": db.scalar(select(func.count()).select_from(EventoNota).where(EventoNota.empresa_id == empresa_id)),
            "nsu": db.get(SyncEstado, empresa_id).ultimo_nsu,
            "situacao": db.get(SyncEstado, empresa_id).situacao,
        }


def _status(empresa_id: int, chave: str) -> Nota:
    with nova_sessao() as db:
        return db.scalar(select(Nota).where(Nota.empresa_id == empresa_id, Nota.chave == chave))


def _popular(adn: ADNSimulado, cnpj: str, n_notas: int, cancelar_a_cada: int = 0) -> list[str]:
    chaves = []
    for i in range(n_notas):
        ch = chave_fake(i + 1, cnpj)
        adn.adicionar_nota(cnpj, ch, numero=i + 1)
        chaves.append(ch)
        if cancelar_a_cada and i % cancelar_a_cada == 0:
            adn.adicionar_evento(cnpj, ch, "101101")
    return chaves


# --- Paginação --------------------------------------------------------------------------

def test_nenhum_documento_pulado_entre_paginas(base):
    adn = ADNSimulado()
    chaves = _popular(adn, C1, 130, cancelar_a_cada=10)  # 143 documentos = 3 páginas cheias + 1
    total = len(adn.docs[C1])
    assert _rodar(adn, base[C1]) == "concluido"
    c = _contagens(base[C1])
    assert c["docs"] == total and c["notas"] == 130 and c["eventos"] == 13
    assert c["nsu"] == total and c["situacao"] == "em_dia"
    # NSU exclusivo: cada chamada usa o maior NSU recebido, sem +1
    assert [n for cnpj, n in adn.chamadas if cnpj == C1] == [0, 50, 100, 143]
    with nova_sessao() as db:
        nsus = sorted(db.scalars(select(DocumentoDfe.nsu).where(DocumentoDfe.empresa_id == base[C1])))
        assert nsus == list(range(1, total + 1))
        canceladas = db.scalar(select(func.count()).select_from(Nota).where(Nota.empresa_id == base[C1], Nota.status == "cancelada"))
        assert canceladas == 13
        n = db.scalar(select(Nota).where(Nota.chave == chaves[5]))
        assert n.papel == "prestada" and str(n.valor_servico) == "100.00" and n.numero == "6"


def test_busca_incremental_continua_do_nsu_salvo(base):
    adn = ADNSimulado()
    _popular(adn, C1, 20)
    _rodar(adn, base[C1])
    _popular_extra = [adn.adicionar_nota(C1, chave_fake(500 + i, C1)) for i in range(5)]
    with nova_sessao() as db:
        j = enfileirar(db, base[C1], "incremental"); db.commit(); jid = j.id
    assert _rodar(adn, base[C1], jid) == "concluido"
    assert _contagens(base[C1])["notas"] == 25
    assert [n for cnpj, n in adn.chamadas if cnpj == C1][-2:] == [20, 25]


# --- Status por eventos -------------------------------------------------------------------

def test_cancelamento_recebido_antes_da_nota_e_aplicado(base):
    adn = ADNSimulado()
    ch = chave_fake(999, C1)
    adn.adicionar_evento(C1, ch, "101101")          # NSU 1: evento chega primeiro
    _popular(adn, C1, 60)                            # empurra a nota para outra página
    adn.adicionar_nota(C1, ch, numero=999)           # NSU 62
    _rodar(adn, base[C1])
    assert _status(base[C1], ch).status == "cancelada"


def test_analise_fiscal_e_indeferido_nao_cancelam(base):
    adn = ADNSimulado()
    a, b, c = chave_fake(1, C1), chave_fake(2, C1), chave_fake(3, C1)
    for ch in (a, b, c):
        adn.adicionar_nota(C1, ch)
    adn.adicionar_evento(C1, a, "101103", dh="2026-10-06T10:00:00-03:00")
    adn.adicionar_evento(C1, b, "101103", dh="2026-10-06T10:00:00-03:00")
    adn.adicionar_evento(C1, b, "105105", dh="2026-10-07T10:00:00-03:00")
    adn.adicionar_evento(C1, c, "101103", dh="2026-10-06T10:00:00-03:00")
    adn.adicionar_evento(C1, c, "105104", dh="2026-10-08T10:00:00-03:00")
    _rodar(adn, base[C1])
    na, nb, nc = (_status(base[C1], x) for x in (a, b, c))
    assert (na.status, na.em_analise_fiscal) == ("autorizada", True)     # só a solicitação
    assert (nb.status, nb.em_analise_fiscal) == ("autorizada", False)    # indeferido
    assert (nc.status, nc.status_detalhe) == ("cancelada", "Cancelamento deferido por análise fiscal")


def test_status_independe_da_ordem_de_chegada():
    from datetime import datetime, timezone
    d = lambda dia: datetime(2026, 10, dia, tzinfo=timezone.utc)  # noqa: E731
    casos = [
        ([("101103", 1), ("105105", 2)], ("autorizada", False)),
        ([("101103", 1), ("105104", 2)], ("cancelada", False)),
        ([("203206", 1)], ("rejeitada", False)),
        ([("203206", 1), ("205208", 2)], ("autorizada", False)),
        ([("203206", 1), ("101101", 2)], ("cancelada", False)),
        ([("105102", 1), ("202201", 2)], ("cancelada", False)),
        ([("999999", 1)], ("autorizada", False)),  # desconhecido não altera
        ([("305101", 1)], ("cancelada", False)),
    ]
    for evs, esperado in casos:
        base_evs = [EventoStatus(c, d(dia), i) for i, (c, dia) in enumerate(evs)]
        for perm in itertools.permutations(base_evs):
            s = calcular_status(list(perm))
            assert (s.status, s.em_analise_fiscal) == esperado, (evs, perm)
    s = calcular_status([EventoStatus("305102", d(1), 1)])
    assert s.bloqueada and s.status == "autorizada"
    assert not calcular_status([EventoStatus("305102", d(1), 1), EventoStatus("305103", d(2), 2)]).bloqueada


# --- Retomada --------------------------------------------------------------------------------

def test_fechar_no_meio_e_reabrir_retoma_sem_duplicar(base):
    adn = ADNSimulado()
    _popular(adn, C1, 180, cancelar_a_cada=7)
    total = len(adn.docs[C1])
    adn.roteiro = [None, None, "morrer"]  # morre na 3ª chamada (processo encerrado)
    jid = _job(base[C1])
    with pytest.raises(FalhaSimulada):
        _rodar(adn, base[C1], jid)
    parcial = _contagens(base[C1])
    assert parcial["nsu"] == 100 and parcial["docs"] == 100

    # "Reabrir o sistema": o gerenciador devolve o job "rodando" para a fila
    g = Gerenciador(nova_sessao, adn.fabrica, buscar_ao_abrir=False, tick=0.05, pausa=0, dormir=lambda s: None)
    with nova_sessao() as db:
        assert db.get(BuscaJob, jid).status == "rodando"
    g.iniciar()
    try:
        _esperar(lambda: _status_job(jid) == "concluido")
    finally:
        g.parar()
    c = _contagens(base[C1])
    assert c["docs"] == total and c["nsu"] == total
    assert c["notas"] == 180 and c["eventos"] == len([d for d in adn.docs[C1] if d.tipo == "EVENTO"])
    chamadas = [n for cnpj, n in adn.chamadas if cnpj == C1]
    assert chamadas.count(100) == 1 and 0 in chamadas  # recomeçou do NSU salvo, não do zero


def test_falha_ao_gravar_nao_avanca_nsu(base, monkeypatch):
    adn = ADNSimulado()
    _popular(adn, C1, 120)
    from app.jobs import sincronizador as s
    original, falhou = s.processar_documento, {"vez": False}

    def quebrar(db, empresa, doc, chaves, r):
        if doc.nsu == 75 and not falhou["vez"]:
            falhou["vez"] = True
            raise OSError("disco cheio")
        return original(db, empresa, doc, chaves, r)

    monkeypatch.setattr(s, "processar_documento", quebrar)
    assert _rodar(adn, base[C1]) == "erro"
    c = _contagens(base[C1])
    assert c["nsu"] == 50 and c["docs"] == 50 and c["situacao"] == "erro"  # a página 51–100 voltou inteira
    with nova_sessao() as db:
        j = enfileirar(db, base[C1], "incremental"); db.commit(); jid = j.id
    assert _rodar(adn, base[C1], jid) == "concluido"
    c = _contagens(base[C1])
    assert c["docs"] == 120 and c["notas"] == 120


def test_refazer_do_zero_nao_duplica(base):
    adn = ADNSimulado()
    _popular(adn, C1, 70, cancelar_a_cada=5)
    _rodar(adn, base[C1])
    antes = _contagens(base[C1])
    with nova_sessao() as db:
        j = enfileirar(db, base[C1], "refazer"); db.commit(); jid = j.id
    assert _rodar(adn, base[C1], jid) == "concluido"
    assert _contagens(base[C1]) == antes
    assert [n for cnpj, n in adn.chamadas if cnpj == C1].count(0) == 2


# --- Erros do ADN -------------------------------------------------------------------------------

def test_429_e_5xx_sao_tolerados(base):
    adn = ADNSimulado()
    _popular(adn, C1, 60)
    esperas = []
    adn.roteiro = ["429:7", "503", "rede", None, "500"]
    from app.adn.cliente import ClienteADN
    import httpx

    def fabrica(pfx, senha):
        return ClienteADN(base_url="https://adn.simulado", transport=httpx.MockTransport(lambda r: adn._responder(r, "x")),
                          dormir=esperas.append)
    st = executar_job(_job(base[C1]), nova_sessao, Contexto(fabrica=fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))
    assert st == "concluido"
    assert _contagens(base[C1])["notas"] == 60
    assert esperas[0] == 7.0  # Retry-After respeitado
    assert len(esperas) == 4 and esperas[1:3] == [14.0, 28.0]  # espera crescente


def test_5xx_persistente_vira_erro_retomavel(base):
    adn = ADNSimulado()
    _popular(adn, C1, 10)
    adn.roteiro = ["503"] * 6
    assert _rodar(adn, base[C1]) == "erro"
    c = _contagens(base[C1])
    assert c["situacao"] == "erro" and c["nsu"] == 0
    with nova_sessao() as db:
        j = enfileirar(db, base[C1], "incremental"); db.commit(); jid = j.id
    assert _rodar(adn, base[C1], jid) == "concluido"


def test_e2245_vira_procuracao_pendente(base, cliente):
    adn = ADNSimulado(sem_procuracao={C2})
    assert _rodar(adn, base[C2]) == "erro"
    with nova_sessao() as db:
        s = db.get(SyncEstado, base[C2])
        assert s.situacao == "sem_procuracao" and "E2245" in s.ultimo_erro
    assert [e["cnpj"] for e in cliente.get("/api/empresas", params={"filtro": "procuracao_pendente"}).json()] == [C2]
    # Não repete sozinha: nenhum job novo na fila
    assert _job(base[C2]) is None


def test_erro_de_tls_vira_erro_de_certificado_sem_retentar(base):
    adn = ADNSimulado()
    adn.roteiro = ["tls"]
    _popular(adn, C1, 3)
    assert _rodar(adn, base[C1]) == "erro"
    assert _contagens(base[C1])["situacao"] == "erro_certificado"
    assert adn.roteiro == []  # só uma tentativa
    # O outro job na fila com o mesmo certificado também é parado
    with nova_sessao() as db:
        j2 = db.scalar(select(BuscaJob).where(BuscaJob.empresa_id == base[C2]).order_by(BuscaJob.id.desc()))
        assert j2.status == "erro" and db.get(SyncEstado, base[C2]).situacao == "erro_certificado"


def test_certificado_vencido_nao_chama_o_adn(base, cliente):
    adn = ADNSimulado()
    with nova_sessao() as db:
        from app.models import Certificado
        from datetime import datetime, timezone
        c = db.scalar(select(Certificado).where(Certificado.titular_doc == C3))
        c.validade = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.commit()
    assert _rodar(adn, base[C3]) == "erro"
    assert _contagens(base[C3])["situacao"] == "erro_certificado" and adn.chamadas == []


# --- Concorrência -----------------------------------------------------------------------------

def _status_job(jid):
    with nova_sessao() as db:
        return db.get(BuscaJob, jid).status


def _esperar(cond, timeout=30):
    fim = time.time() + timeout
    while time.time() < fim:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("tempo esgotado")


def test_mesmo_certificado_nao_roda_em_paralelo(base):
    adn = ADNSimulado(atraso=0.02, lote=10)
    for cnpj in (C1, C2, C3, CONTAB):
        _popular(adn, cnpj, 60)
    g = Gerenciador(nova_sessao, adn.fabrica, max_total=2, buscar_ao_abrir=False, tick=0.02, pausa=0, dormir=lambda s: None)
    g.iniciar()
    try:
        _esperar(lambda: all(_contagens(base[k])["situacao"] == "em_dia" for k in (C1, C2, C3, "contab")), timeout=60)
    finally:
        g.parar()
    # C1, C2 e a contabilidade usam o mesmo certificado; C3 usa o próprio
    assert all(v == 1 for v in adn.max_por_cert.values()), adn.max_por_cert
    assert adn.max_total == 2  # o certificado próprio rodou junto com o da contabilidade
    for k in (C1, C2, C3, "contab"):
        assert _contagens(base[k])["notas"] == 60


# --- API ------------------------------------------------------------------------------------

def test_api_de_buscas(base, cliente):
    r = cliente.get("/api/buscas").json()
    assert r["na_fila"] == 4 and r["rodando"] == 0
    jid = _job(base[C1])
    assert cliente.post(f"/api/buscas/{jid}/pausar").json()["status"] == "pausado"
    assert cliente.post(f"/api/buscas/{jid}/pausar").status_code == 409
    assert cliente.post(f"/api/buscas/{jid}/retomar").json()["status"] == "fila"
    # Buscar agora com job pendente reaproveita o mesmo job
    assert cliente.post(f"/api/empresas/{base[C1]}/buscas", json={"tipo": "incremental"}).json()["id"] == jid
    assert cliente.post(f"/api/empresas/{base[C1]}/buscas", json={"tipo": "x"}).status_code == 422
    adn = ADNSimulado()
    _popular(adn, C1, 3)
    _rodar(adn, base[C1], jid)
    log = cliente.get(f"/api/buscas/{jid}/log").json()
    assert any("Fim da fila" in l["mensagem"] for l in log)
    assert cliente.get("/api/buscas").json()["recentes"][0]["notas_ok"] == 3
    # Refazer cria um job novo
    novo = cliente.post(f"/api/empresas/{base[C1]}/buscas", json={"tipo": "refazer"}).json()
    assert novo["id"] != jid and novo["tipo"] == "refazer"


def test_ssl_context_carrega_pfx_sem_deixar_arquivo(tmp_path, monkeypatch):
    import tempfile
    from app.adn.cliente import ssl_context
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ctx = ssl_context(criar_pfx("X", cnpj=C1), SENHA)
    assert ctx.minimum_version.name == "TLSv1_2"
    assert list(tmp_path.iterdir()) == []
