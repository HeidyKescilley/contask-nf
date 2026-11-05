"""Dashboard mensal por competência."""
from decimal import Decimal

import pytest

from app.core.db import nova_sessao
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob
from tests.adn_simulado import ADNSimulado, chave_fake, evento_xml, nfse_xml
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
EMP = dv_cnpj("114447770001")
OUTRA = "33000167000101"


@pytest.fixture()
def emp(cliente):
    cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": SENHA},
                 files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    eid = cliente.post("/api/empresas", data={"cnpj": EMP, "razao_social": "Empresa", "modo_certificado": "contabilidade"}).json()["empresa"]["id"]
    adn = ADNSimulado()
    seq = iter(range(1, 1000))

    def nota(prest, toma, valor, dh):
        ch = chave_fake(next(seq), EMP)
        adn.adicionar(EMP, "NFSE", ch, nfse_xml(ch, prest=prest, toma=toma, valor=valor, dh=dh))
        return ch

    # Outubro/2026 (competência = data da emissão nos XMLs de teste)
    nota(EMP, OUTRA, "1000.00", "2026-10-02T10:00:00-03:00")
    nota(EMP, OUTRA, "250.50", "2026-10-15T10:00:00-03:00")
    c_canc = nota(EMP, OUTRA, "999.99", "2026-10-20T10:00:00-03:00")      # cancelada
    c_rej = nota(EMP, OUTRA, "80.00", "2026-10-21T10:00:00-03:00")        # rejeitada
    nota(OUTRA, EMP, "300.00", "2026-10-31T23:59:00-03:00")              # tomada no último minuto do mês
    c_tom_canc = nota(OUTRA, EMP, "45.00", "2026-10-05T10:00:00-03:00")   # tomada cancelada
    # Outros meses
    nota(EMP, OUTRA, "10.00", "2026-09-30T23:00:00-03:00")
    nota(EMP, OUTRA, "20.00", "2026-05-10T10:00:00-03:00")
    nota(EMP, OUTRA, "30.00", "2026-04-10T10:00:00-03:00")              # fora da janela de 6 meses
    nota(EMP, OUTRA, "40.00", "2026-11-01T00:00:00-03:00")
    adn.adicionar(EMP, "EVENTO", c_canc, evento_xml(c_canc, "101101", dh="2026-10-25T10:00:00-03:00"), "CANCELAMENTO")
    adn.adicionar(EMP, "EVENTO", c_rej, evento_xml(c_rej, "203206", dh="2026-10-26T10:00:00-03:00"), "REJEICAO_TOMADOR")
    adn.adicionar(EMP, "EVENTO", c_tom_canc, evento_xml(c_tom_canc, "101101", dh="2026-11-02T10:00:00-03:00"), "CANCELAMENTO")
    with nova_sessao() as db:
        jid = db.query(BuscaJob.id).filter(BuscaJob.empresa_id == eid, BuscaJob.status == "fila").scalar()
    executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))
    return eid


def test_totais_do_mes(cliente, emp):
    d = cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2026-10"}).json()
    assert d["base"] == "competencia" and d["inicio"] == "2026-10-01" and d["fim"] == "2026-10-31"
    assert d["total_nfse"] == 6
    assert d["eventos_mes"] == 2 and d["total_xmls"] == 8  # evento de novembro fica fora
    assert d["prestados"]["quantidade"] == 2 and Decimal(str(d["prestados"]["valor"])) == Decimal("1250.50")
    assert d["tomados"]["quantidade"] == 1 and Decimal(str(d["tomados"]["valor"])) == Decimal("300.00")
    # Cancelada e rejeitada não entram no valor autorizado
    assert Decimal(str(d["valor_autorizado"])) == Decimal("1550.50")
    assert d["canceladas"] == {"quantidade": 2, "valor": pytest.approx(1044.99), "prestadas": 1, "tomadas": 1}
    assert d["rejeitadas"]["quantidade"] == 1 and d["rejeitadas"]["prestadas"] == 1
    assert d["prestados"]["canceladas"] == 1 and d["prestados"]["rejeitadas"] == 1


def test_serie_de_seis_meses(cliente, emp):
    d = cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2026-10"}).json()
    s = d["prestados"]["serie"]
    assert [x["mes"] for x in s] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert [x["quantidade"] for x in s] == [1, 0, 0, 0, 1, 2]
    assert [x["quantidade"] for x in d["tomados"]["serie"]][-1] == 1


def test_cards_abrem_a_lista_com_os_mesmos_numeros(cliente, emp):
    """O link de cada card usa competência + período do mês + status: a lista deve bater com o card."""
    d = cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2026-10"}).json()
    base = {"campo_data": "competencia", "inicio": d["inicio"], "fim": d["fim"]}
    for papel, chave in (("prestada", "prestados"), ("tomada", "tomados")):
        l = cliente.get(f"/api/empresas/{emp}/notas", params={**base, "papel": papel, "status": "autorizada"}).json()
        assert l["total"] == d[chave]["quantidade"]
        assert Decimal(str(l["totais"]["valor_autorizado"])) == Decimal(str(d[chave]["valor"]))
    for status, chave in (("cancelada", "canceladas"), ("rejeitada", "rejeitadas")):
        for papel, sub in (("prestada", "prestadas"), ("tomada", "tomadas")):
            l = cliente.get(f"/api/empresas/{emp}/notas", params={**base, "papel": papel, "status": status}).json()
            assert l["total"] == d[chave][sub], (status, papel)


def test_mes_vazio_sugere_ultimo_mes_com_notas(cliente, emp):
    d = cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2027-03"}).json()
    assert d["total_nfse"] == 0 and d["ultimo_mes_com_notas"] == "2026-11"
    assert cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2026-13"}).status_code == 422
    assert cliente.get("/api/empresas/999/dashboard").status_code == 404


def test_dezembro_vira_o_ano(cliente, emp):
    d = cliente.get(f"/api/empresas/{emp}/dashboard", params={"mes": "2026-12"}).json()
    assert d["fim"] == "2026-12-31"
    assert [x["mes"] for x in d["prestados"]["serie"]][0] == "2026-07"
