"""Substituição de NFS-e: grupo subst na DPS (Sefin nos dois leiautes e ISSNet do DF) e o fluxo pela API."""
from datetime import datetime

import pytest
from lxml import etree

from app.core import config as cfgmod
from app.emissor import assinatura
from app.emissor.dps import (
    NT004, NT009, PRODUCAO, RESTRITA, BRASILIA, DpsInvalida, Substituicao, montar, montar_issnet, validar_xsd,
    validar_xsd_issnet,
)
from app.emissor.issnet import mensagens as issnet_msg
from tests.certs import criar_pfx
from tests.test_emissor_cadastros import OUTRO
from tests.test_emissor_issnet import _dados_issnet
from tests.test_emissor_motor import NS, _assinada, _dados, _emissao, _pronta, sefin  # noqa: F401
from tests.test_empresas import SENHA

CHAVE_ORIGINAL = "5300108" + "2" + "2" + OUTRO + "0" * 27  # 50 dígitos
SUBST = Substituicao(CHAVE_ORIGINAL, "99", "Tomador informado com o CNPJ errado na nota original.")


def _com_subst(d):
    d.subst = SUBST
    return d


@pytest.mark.parametrize("leiaute", [NT004, NT009])
def test_subst_vai_depois_de_cLocEmi_nos_dois_leiautes(leiaute):
    raiz = montar(_com_subst(_dados(RESTRITA)), leiaute)
    chave, cert = assinatura.carregar_chave(criar_pfx("EMPRESA PROPRIA LTDA", cnpj=OUTRO), SENHA)
    assinatura.assinar(raiz, raiz[0], chave, cert)
    validar_xsd(raiz, RESTRITA, leiaute=leiaute)
    filhos = [c.tag.split("}")[1] for c in raiz[0]]
    assert filhos[filhos.index("cLocEmi") + 1] == "subst"
    s = raiz[0].find("n:subst", NS)
    assert [s.find(f"n:{t}", NS).text for t in ("chSubstda", "cMotivo")] == [CHAVE_ORIGINAL, "99"]


def test_subst_no_issnet():
    raiz = montar_issnet(_com_subst(_dados_issnet()))
    chave, cert = assinatura.carregar_chave(criar_pfx("EMPRESA PROPRIA LTDA", cnpj=OUTRO), SENHA)
    assinatura.assinar(raiz, raiz[0], chave, cert, assinatura.ISSNET)
    validar_xsd_issnet(etree.fromstring(issnet_msg.gerar_nfse(raiz).encode("utf-8")))
    assert raiz[0].find("n:subst/n:chSubstda", NS).text == CHAVE_ORIGINAL


@pytest.mark.parametrize("subst, msg", [
    (Substituicao("123", "99", "Justificativa longa o bastante."), "50 dígitos"),
    (Substituicao(CHAVE_ORIGINAL, "07", "Justificativa longa o bastante."), "motivo"),
    (Substituicao(CHAVE_ORIGINAL, "99", "curta"), "15 a 255"),
])
def test_subst_invalida(subst, msg):
    d = _dados(RESTRITA)
    d.subst = subst
    with pytest.raises(DpsInvalida, match=msg):
        montar(d)


def _subst(**kw):
    return {"motivo": "99", "justificativa": "Tomador informado com o CNPJ errado.", **kw}


def test_substituir_nota_do_contask(cliente, sefin):
    e, s = _pronta(cliente)
    original = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert original["situacao"] == "autorizada"
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, descricao="Honorários contábeis (corrigida)",
                                                         substituicao=_subst(nota_id=original["id"])))
    assert r.status_code == 201, r.text
    nova = r.json()
    assert nova["situacao"] == "autorizada" and nova["numero"] == 2
    assert nova["subst_chave"] == original["chave"] and nova["substitui"]["id"] == original["id"]
    inf = etree.fromstring(sefin.recebidas[-1])[0]
    assert inf.find("n:subst/n:chSubstda", NS).text == original["chave"]
    assert inf.find("n:subst/n:xMotivo", NS).text == "Tomador informado com o CNPJ errado."
    o = cliente.get(f"/api/emissor/notas/{original['id']}").json()
    assert o["situacao"] == "cancelada" and o["substituida_por"]["id"] == nova["id"]
    assert o["motivo_cancelamento"].startswith("Substituída pela NFS-e nº 42")
    assert cliente.get(f"/api/emissor/notas/{original['id']}/danfse").status_code == 200
    # a original já foi substituída
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_id=original["id"])))
    assert r.status_code == 409


def test_substituta_rejeitada_mantem_a_original(cliente, sefin):
    e, s = _pronta(cliente)
    original = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    sefin.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_id=original["id"]))).json()
    assert n["situacao"] == "rejeitada" and n["subst_chave"] == original["chave"]
    assert cliente.get(f"/api/emissor/notas/{original['id']}").json()["situacao"] == "autorizada"
    # corrigida e reenviada com o mesmo número, continua substituta
    sefin.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n['id']}/reenviar", json=_emissao(e, s))
    assert r.json()["situacao"] == "autorizada"
    assert etree.fromstring(sefin.recebidas[-1])[0].find("n:subst/n:chSubstda", NS).text == original["chave"]
    assert cliente.get(f"/api/emissor/notas/{original['id']}").json()["situacao"] == "cancelada"


def test_substituicao_validada_antes_de_gastar_numero(cliente, sefin):
    e, s = _pronta(cliente)
    original = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    enviadas = len(sefin.recebidas)
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_id=original["id"], justificativa="curta")))
    assert r.status_code == 422
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_id=999)))
    assert r.status_code == 404
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst()))
    assert r.status_code == 422
    assert len(sefin.recebidas) == enviadas
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == 2


def test_substituir_nota_do_adn(cliente, sefin, monkeypatch):
    from app.core.db import nova_sessao
    from app.models import Nota
    e, s = _pronta(cliente)
    chave = "5300108" + "1" + "2" + OUTRO + "0" * 26 + "7"
    with nova_sessao() as db:
        n = Nota(empresa_id=e["id"], chave=chave, papel="prestada", status="autorizada", numero="88", serie="1",
                 data_emissao=datetime(2026, 11, 10, 9, 30, tzinfo=BRASILIA), competencia=datetime(2026, 11, 10).date(),
                 valor_servico=1000, valor_liquido=1000)
        db.add(n)
        db.commit()
        adn_id = n.id
    # ADN é produção: na homologação não dá
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_adn_id=adn_id)))
    assert r.status_code == 409 and "produção" in r.json()["detail"]
    monkeypatch.setenv("CONTASK_EMISSOR_PRODUCAO", "true")
    cfgmod.config.cache_clear()
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, substituicao=_subst(nota_adn_id=adn_id)))
    assert r.status_code == 201, r.text
    assert r.json()["situacao"] == "autorizada" and r.json()["subst_chave"] == chave
    inf = etree.fromstring(sefin.recebidas[-1])[0]
    assert inf.find("n:tpAmb", NS).text == "1" and inf.find("n:subst/n:chSubstda", NS).text == chave
