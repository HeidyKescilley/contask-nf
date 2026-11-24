"""Tomador no exterior: NIF ou cNaoNIF, endereço no exterior (endExt), grupo comExt e exportação de serviço."""
from decimal import Decimal

import pytest
from lxml import etree

from app.emissor import issnet
from app.emissor.dps import (
    PRODUCAO, RESTRITA, ComercioExterior, DpsInvalida, TomadorDps, montar, montar_issnet, validar_xsd, validar_xsd_issnet,
)
from tests.test_emissor_motor import NS, _assinada, _dados, sefin  # noqa: F401 (fixture)

ESTRANGEIRO = dict(documento="", nome="ACME Corporation", pais="US", nif="98-7654321", cod_postal="10001",
                   cidade="New York", estado_provincia="NY", logradouro="5th Avenue", numero="350", bairro="Midtown",
                   email="ap@acme.example")


def _exterior(amb=RESTRITA, op="1", exportacao=True, **tomador):
    d = _dados(amb, op=op)
    d.tomador = TomadorDps(**{**ESTRANGEIRO, **tomador})
    d.comex = ComercioExterior(valor_moeda=Decimal("190.50"), moeda="220")
    d.exportacao = exportacao
    if op == "1":
        d.cindop, d.cclasstrib = "100301", "410027"  # exportação de serviço (IBS/CBS)
    return d


@pytest.mark.parametrize("amb", [RESTRITA, PRODUCAO])
def test_dps_com_tomador_no_exterior_passa_no_xsd(amb):
    raiz = _assinada(_exterior(amb))
    validar_xsd(raiz, amb)
    inf = raiz[0]
    toma = inf.find("n:toma", NS)
    assert toma.findtext("n:NIF", namespaces=NS) == "98-7654321" and toma.find("n:CNPJ", NS) is None
    ext = toma.find("n:end/n:endExt", NS)
    assert [ext.findtext(f"n:{t}", namespaces=NS) for t in ("cPais", "cEndPost", "xCidade", "xEstProvReg")] == ["US", "10001", "New York", "NY"]
    ce = inf.find("n:serv/n:comExt", NS)
    assert ce.findtext("n:tpMoeda", namespaces=NS) == "220" and ce.findtext("n:vServMoeda", namespaces=NS) == "190.50"
    assert [etree.QName(e).localname for e in inf.find("n:serv", NS)][:3] == ["locPrest", "cServ", "comExt"]
    tm = inf.find("n:valores/n:trib/n:tribMun", NS)
    assert tm.findtext("n:tribISSQN", namespaces=NS) == "3" and tm.findtext("n:cPaisResult", namespaces=NS) == "US"


def test_sem_nif_vai_o_motivo_e_sem_exportacao_e_tributavel():
    raiz = _assinada(_exterior(PRODUCAO, op="3", exportacao=False, nif=None, nao_nif="1"))
    validar_xsd(raiz, PRODUCAO)
    inf = raiz[0]
    assert inf.findtext("n:toma/n:cNaoNIF", namespaces=NS) == "1" and inf.find("n:toma/n:NIF", NS) is None
    tm = inf.find("n:valores/n:trib/n:tribMun", NS)
    assert tm.findtext("n:tribISSQN", namespaces=NS) == "1" and tm.find("n:cPaisResult", NS) is None


def test_issnet_df_com_tomador_no_exterior():
    d = _exterior(RESTRITA)
    d.ctribmun = "1602"
    with pytest.raises(DpsInvalida, match="sem vínculo"):  # o ISSNet não tem o código 0
        montar_issnet(d)
    d.comex.vinculo = "9"
    raiz = montar_issnet(d)
    validar_xsd_issnet(etree.fromstring(issnet.mensagens.gerar_nfse(raiz).encode("utf-8")))
    assert raiz[0].findtext("n:toma/n:end/n:endExt/n:cPais", namespaces=NS) == "US"


@pytest.mark.parametrize("ajuste, trecho", [
    ({"nif": None}, "NIF"),
    ({"cidade": None}, "endereço completo"),
])
def test_regras_do_tomador_no_exterior(ajuste, trecho):
    with pytest.raises(DpsInvalida, match=trecho):
        montar(_exterior(**ajuste))


def test_exterior_exige_comex_e_nao_retem_iss():
    d = _exterior()
    d.comex = None
    with pytest.raises(DpsInvalida, match="E0330"):
        montar(d)
    d = _dados(RESTRITA)
    d.exportacao = True
    with pytest.raises(DpsInvalida, match="só com tomador no exterior"):
        montar(d)


# ---------------------------------------------------------------------------
# Pela API (empresa do Simples, canal nacional, Sefin simulada)
# ---------------------------------------------------------------------------

TOMADOR_API = {"documento": "", "nome": "ACME Corporation", "pais": "US", "nif": "98-7654321", "cod_postal": "10001",
               "cidade": "New York", "estado_provincia": "NY", "logradouro": "5th Avenue", "numero": "350", "bairro": "Midtown"}
COMEX = {"moeda": "220", "valor_moeda": "190.50", "exportacao": True}


def test_emissao_com_tomador_no_exterior_pela_api(cliente, sefin):
    from tests.test_emissor_motor import _emissao, _pronta
    e, s = _pronta(cliente)
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=TOMADOR_API))
    assert r.status_code == 422 and "moeda" in r.json()["detail"] and sefin.recebidas == []
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=TOMADOR_API, comercio_exterior=COMEX))
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["situacao"] == "autorizada" and n["tomador"]["pais"] == "US" and n["comercio_exterior"]["exportacao"] is True
    inf = etree.fromstring(sefin.recebidas[-1])[0]
    assert inf.findtext("n:toma/n:NIF", namespaces=NS) == "98-7654321"
    assert inf.findtext("n:serv/n:comExt/n:vServMoeda", namespaces=NS) == "190.50"
    assert inf.findtext("n:valores/n:trib/n:tribMun/n:tribISSQN", namespaces=NS) == "3"
    # o tomador fica salvo para as próximas notas
    t = cliente.get("/api/emissor/tomadores", params={"q": "ACME"}).json()
    assert t[0]["pais"] == "US" and t[0]["documento"] == "EXUS987654321"
    # prévia também
    assert cliente.post("/api/emissor/notas/previa", json=_emissao(e, s, tomador=TOMADOR_API, comercio_exterior=COMEX)).status_code == 200


def test_validacoes_do_tomador_no_exterior_pela_api(cliente, sefin):
    from tests.test_emissor_motor import _emissao, _pronta
    e, s = _pronta(cliente)
    for ajuste, trecho in (({"pais": "XX"}, "país"), ({"pais": "BR", "documento": ""}, "CNPJ ou CPF"),
                           ({"nif": None}, "NIF"), ({"cidade": ""}, "E0242")):
        r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador={**TOMADOR_API, **ajuste}, comercio_exterior=COMEX))
        assert r.status_code == 422 and trecho in r.json()["detail"], (ajuste, r.text)
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador={**TOMADOR_API, "nif": None, "nao_nif": "1"},
                                                          comercio_exterior={**COMEX, "exportacao": False}))
    assert r.status_code == 201, r.text
    assert etree.fromstring(sefin.recebidas[-1])[0].findtext("n:toma/n:cNaoNIF", namespaces=NS) == "1"
    paises = cliente.get("/api/emissor/codigos/exterior").json()
    assert "US" in {p["codigo"] for p in paises["paises"]}
    assert "BR" not in {p["codigo"] for p in paises["paises"]} and paises["moedas"][0]["codigo"] == "220"
