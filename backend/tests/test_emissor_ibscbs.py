"""Grupo IBS/CBS na DPS nacional para quem não é do Simples (regime regular)."""
import pytest

from app.emissor.dps import PRODUCAO, RESTRITA, DpsInvalida, montar, validar_xsd
from tests.test_emissor_motor import NS, _assinada, _dados, sefin  # noqa: F401 (fixture)

N = NS  # já é {"n": namespace}


def _regular(amb, cindop="100301", cclasstrib="000001"):
    d = _dados(amb, op="1")
    d.cindop, d.cclasstrib = cindop, cclasstrib
    return d


@pytest.mark.parametrize("amb", [RESTRITA, PRODUCAO])
def test_regime_regular_leva_o_grupo_ibscbs_nos_dois_leiautes(amb):
    raiz = _assinada(_regular(amb))
    validar_xsd(raiz, amb)
    inf = raiz[0]
    ib = inf.find("n:IBSCBS", N)
    assert inf[-2] is ib or inf[-1] is ib  # último grupo do infDPS (a assinatura fica fora do infDPS)
    assert ib.findtext("n:cIndOp", namespaces=N) == "100301" and ib.findtext("n:indDest", namespaces=N) == "0"
    if amb == PRODUCAO:  # NT 004: finNFSe dentro do grupo, CST/cClassTrib em gIBSCBS
        assert ib.findtext("n:finNFSe", namespaces=N) == "0"
        g = ib.find("n:valores/n:trib/n:gIBSCBS", N)
    else:  # NT 009: finNFSe no infDPS, CST/cClassTrib direto em trib
        assert ib.find("n:finNFSe", N) is None and inf.findtext("n:finNFSe", namespaces=N) == "0"
        g = ib.find("n:valores/n:trib", N)
    assert (g.findtext("n:CST", namespaces=N), g.findtext("n:cClassTrib", namespaces=N)) == ("000", "000001")


def test_cst_sem_tributacao_nao_leva_cindop_na_nt009():
    raiz = _assinada(_regular(RESTRITA, cclasstrib="410001"))
    validar_xsd(raiz, RESTRITA)
    ib = raiz[0].find("n:IBSCBS", N)
    assert ib.find("n:cIndOp", N) is None and ib.findtext("n:valores/n:trib/n:CST", namespaces=N) == "410"
    validar_xsd(_assinada(_regular(PRODUCAO, cclasstrib="410001")), PRODUCAO)  # na NT 004 o cIndOp é obrigatório


@pytest.mark.parametrize("op", ["2", "3"])
def test_simples_e_mei_nao_levam_o_grupo(op):
    d = _dados(PRODUCAO, op=op)
    d.cindop, d.cclasstrib = "100301", "000001"
    assert montar(d)[0].find("n:IBSCBS", N) is None


def test_regime_regular_sem_codigos_e_barrado_antes_do_envio():
    d = _regular(PRODUCAO, cindop=None)
    with pytest.raises(DpsInvalida, match="cIndOp e o cClassTrib"):
        montar(d)


# ---------------------------------------------------------------------------
# Cadastro e emissão pela API (empresa de São Paulo no lucro presumido: canal nacional)
# ---------------------------------------------------------------------------

def _presumido(cliente):
    from tests.test_emissor_motor import _pronta
    e, s = _pronta(cliente)
    cfg = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]
    base = {k: cfg[k] for k in ("inscricao_municipal", "op_simples", "reg_ap_trib_sn", "reg_esp_trib", "serie", "proximo_numero")}
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config",
                    json={**base, "regime_tributario": "presumido", "cod_municipio": "3550308"})
    assert r.status_code == 200 and r.json()["config"]["exige_ibscbs"] is True
    return e, s


def test_regime_regular_exige_os_codigos_e_emite_com_o_grupo(cliente, sefin):
    from tests.test_emissor_motor import _emissao
    e, s = _presumido(cliente)
    item = cliente.get(f"/api/emissor/empresas/{e['id']}").json()
    assert any("sem cIndOp e cClassTrib" in a for a in item["avisos"])
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s))
    assert r.status_code == 422 and "cIndOp e o cClassTrib" in r.json()["detail"] and sefin.recebidas == []

    corpo = {"descricao": "Honorários contábeis", "ctribnac": "171901", "cnbs": "113022100"}
    assert cliente.put(f"/api/emissor/servicos/{s['id']}", json=corpo).status_code == 422
    r = cliente.put(f"/api/emissor/servicos/{s['id']}", json={**corpo, "cindop": "100301", "cclasstrib": "000001"})
    assert r.status_code == 200, r.text
    assert not any("cIndOp" in a for a in cliente.get(f"/api/emissor/empresas/{e['id']}").json()["avisos"])

    from tests.test_emissor_motor import CLIENTE
    sem_endereco = cliente.post("/api/emissor/notas", json=_emissao(e, s))
    assert sem_endereco.status_code == 422 and "E0239" in sem_endereco.json()["detail"]
    tomador = {"documento": CLIENTE, "nome": "Tomador Teste Ltda", "cep": "01310100", "cod_municipio": "3550308",
               "logradouro": "Avenida Paulista", "numero": "1000", "bairro": "Bela Vista"}
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, tomador=tomador))
    assert r.status_code == 201, r.text
    from lxml import etree
    ib = etree.fromstring(sefin.recebidas[-1])[0].find("n:IBSCBS", N)
    assert ib.findtext("n:valores/n:trib/n:CST", namespaces=N) == "000"  # homologação: leiaute da NT 009

    # duplicar lê o cClassTrib de volta, nos dois leiautes
    from app.api.emissor_notas import modelo_do_xml
    m = modelo_do_xml(etree.tostring(etree.fromstring(sefin.recebidas[-1])))
    assert (m["cindop"], m["cclasstrib"]) == ("100301", "000001")


def test_incidencia_no_tomador_exige_endereco():
    """E0239 visto na produção restrita: com cIndOp 100301 o IBS incide no endereço do tomador."""
    d = _regular(PRODUCAO)
    d.tomador = None
    with pytest.raises(DpsInvalida, match="E0239"):
        montar(d)
    d = _regular(PRODUCAO, cindop="030101")  # incidência no estabelecimento do prestador: não exige
    d.tomador = None
    validar_xsd(_assinada(d), PRODUCAO)
    d = _regular(PRODUCAO, cclasstrib="410001")  # imunidade/não incidência: sem tributação a detalhar
    d.tomador = None
    montar(d)
