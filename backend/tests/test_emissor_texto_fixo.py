"""Texto fixo da empresa nas informações complementares (dados bancários, observações)."""
from lxml import etree

from app.emissor import textos
from tests.test_emissor_motor import NS, _emissao, _pronta, sefin  # noqa: F401

FIXO = "Dados bancarios: Banco 001 Ag 1234 CC 56789-0 PIX contato@empresa.com.br"


def _config(cliente, e, **extra):
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={
        "op_simples": "3", "reg_ap_trib_sn": "1", "regime_tributario": "simples", "cod_municipio": "5300108", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _infcomp(sefin):
    el = etree.fromstring(sefin.recebidas[-1])[0].find("n:serv/n:infoCompl/n:xInfComp", NS)
    return el.text if el is not None else ""


def test_texto_fixo_em_toda_nota(cliente, sefin):
    e, s = _pronta(cliente)
    item = _config(cliente, e, texto_fixo=f"  {FIXO}\n ")
    assert item["config"]["texto_fixo"] == FIXO
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s, info_complementar="Ref. outubro")).json()
    assert n["situacao"] == "autorizada"
    info = _infcomp(sefin)
    assert info.startswith(f"Ref. outubro {FIXO}") and textos.TEXTO_SIMPLES in info
    # ao duplicar, o texto do usuário volta sem o fixo (ele vem pela marcação)
    assert n["info_usuario"] == "Ref. outubro" and n["texto_fixo"] is True
    # desmarcado na nota: não vai
    cliente.post("/api/emissor/notas", json=_emissao(e, s, texto_fixo=False))
    assert FIXO not in _infcomp(sefin)


def test_salvar_config_sem_o_campo_mantem_o_texto(cliente, sefin):
    e, _ = _pronta(cliente)
    _config(cliente, e, texto_fixo=FIXO)
    assert _config(cliente, e)["config"]["texto_fixo"] == FIXO  # tela antiga sem o campo
    assert _config(cliente, e, texto_fixo="")["config"]["texto_fixo"] is None


def test_nota_duplicada_sem_servico_cadastrado_leva_o_fixo(cliente, sefin):
    e, s = _pronta(cliente)
    _config(cliente, e, texto_fixo=FIXO)
    codigos = {"ctribnac": "171901", "cnbs": "113022100"}
    r = cliente.post("/api/emissor/notas", json={**_emissao(e, s), "servico_id": None, "servico": codigos, "descricao": "Honorários"})
    assert r.status_code == 201, r.text
    assert FIXO in _infcomp(sefin)


def test_compor_e_separar():
    info = textos.compor("Obs", True, True, FIXO)
    assert textos.separar(info, FIXO) == ("Obs", True, True)
    assert textos.tem_fixo(info, FIXO) and not textos.tem_fixo(info, None)
