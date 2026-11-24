"""cIndOp e cClassTrib: listas oficiais pelo cenário da empresa, escolha por nota e duplicação."""
from lxml import etree

from app.emissor import tabelas
from tests.test_emissor_ibscbs import _presumido
from tests.test_emissor_motor import CLIENTE, NS, _emissao, sefin  # noqa: F401

TOMADOR = {"documento": CLIENTE, "nome": "Tomador Teste Ltda", "cep": "01310100", "cod_municipio": "3550308",
           "logradouro": "Avenida Paulista", "numero": "1000", "bairro": "Bela Vista"}


def _ibscbs_enviado(sefin):
    ib = etree.fromstring(sefin.recebidas[-1])[0].find("n:IBSCBS", NS)
    trib = ib.find("n:valores/n:trib", NS)
    g = trib.find("n:gIBSCBS", NS)
    return ib.findtext("n:cIndOp", namespaces=NS), (g if g is not None else trib).findtext("n:cClassTrib", namespaces=NS)


def test_listas_so_com_codigos_da_nfse_e_sugeridos_primeiro(cliente):
    r = cliente.get("/api/emissor/codigos/ibscbs", params={"ctribnac": "040101", "cnbs": "123012100"})
    assert r.status_code == 200
    o = r.json()
    assert o["cindop"][0] == {**tabelas.cindop("030101"), "sugerido": True, "exige_endereco_tomador": False}
    assert o["cclasstrib"][0]["codigo"] == "200029" and o["cclasstrib"][0]["sugerido"]
    cods = {c["codigo"] for c in o["cclasstrib"]}
    assert "000001" in cods and not cods & tabelas.SO_PESSOA_FISICA  # empresa (CNPJ): sem os de autônomo
    assert {c["codigo"] for c in o["cindop"]} >= {"100301", "030101"} and "090101" not in {c["codigo"] for c in o["cindop"]}
    assert next(c for c in o["cindop"] if c["codigo"] == "100301")["exige_endereco_tomador"] is True
    # sem serviço: a lista inteira, nenhuma sugerida
    assert not any(c["sugerido"] for c in cliente.get("/api/emissor/codigos/ibscbs").json()["cindop"])


def test_codigos_da_nota_valem_no_lugar_dos_do_servico(cliente, sefin):
    e, s = _presumido(cliente)
    corpo = {"descricao": "Honorários contábeis", "ctribnac": "171901", "cnbs": "113022100", "cindop": "100301", "cclasstrib": "000001"}
    assert cliente.put(f"/api/emissor/servicos/{s['id']}", json=corpo).status_code == 200
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=TOMADOR, cindop="030101", cclasstrib="200052"))
    assert r.status_code == 201, r.text
    n = r.json()
    assert (n["cindop"], n["cclasstrib"]) == ("030101", "200052") and _ibscbs_enviado(sefin) == ("030101", "200052")
    # o serviço não muda
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/servicos").json()[0]["cclasstrib"] == "000001"
    # em branco: os do serviço
    cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=TOMADOR))
    assert _ibscbs_enviado(sefin) == ("100301", "000001")


def test_codigo_fora_da_tabela_e_barrado(cliente, sefin):
    e, s = _presumido(cliente)
    for campos, trecho in (({"cindop": "999999"}, "cIndOp"), ({"cclasstrib": "12345"}, "6 dígitos"),
                           ({"cclasstrib": "200055"}, "pessoa física")):
        r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=TOMADOR, **campos))
        assert r.status_code == 422 and trecho in r.json()["detail"], r.text
        r = cliente.post("/api/emissor/notas/previa", json=_emissao(e, s, tomador=TOMADOR, **campos))
        assert r.status_code == 422
    corpo = {"descricao": "Honorários", "ctribnac": "171901", "cnbs": "113022100", "cindop": "999999", "cclasstrib": "000001"}
    assert cliente.put(f"/api/emissor/servicos/{s['id']}", json=corpo).status_code == 422
    assert sefin.recebidas == []


def test_edicao_do_servico_troca_os_codigos(cliente, sefin):
    e, s = _presumido(cliente)
    corpo = {"descricao": "Consultoria", "ctribnac": "171901", "cnbs": "113022100", "cindop": "100301", "cclasstrib": "000001"}
    r = cliente.put(f"/api/emissor/servicos/{s['id']}", json={**corpo, "cclasstrib": "200052"})
    assert r.status_code == 200 and r.json()["cclasstrib"] == "200052" and r.json()["descricao"] == "Consultoria"
