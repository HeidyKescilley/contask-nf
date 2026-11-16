"""Duplicar sem serviço cadastrado (os códigos vêm da nota) e pré-preencher o emissor com a última nota."""
from datetime import datetime

from lxml import etree

from app.core.config import config
from app.core.db import nova_sessao
from app.emissor.dps import BRASILIA, montar, serializar
from app.models import Nota
from tests.test_emissor_motor import NS, _dados, _emissao, _pronta, sefin  # noqa: F401 (fixture)

CODIGOS = {"ctribnac": "171901", "cnbs": "113022100"}


def _sem_servico(e, **extra):
    corpo = _emissao(e, {"id": None}, **{"descricao": "Honorários de outubro", "servico": CODIGOS, **extra})
    corpo.pop("servico_id")
    return corpo


def test_emite_com_os_codigos_da_nota_sem_servico_cadastrado(cliente, sefin):
    e, s = _pronta(cliente)
    assert cliente.delete(f"/api/emissor/servicos/{s['id']}").status_code == 204
    item = cliente.get(f"/api/emissor/empresas/{e['id']}").json()
    assert not any("serviço" in p for p in item["pendencias"]) and any("Nenhum serviço" in a for a in item["avisos"])

    r = cliente.post("/api/emissor/notas", json=_sem_servico(e))
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["situacao"] == "autorizada" and n["servico_id"] is None
    assert (n["ctribnac"], n["cnbs"], n["descricao"]) == ("171901", "113022100", "Honorários de outubro")
    cs = etree.fromstring(sefin.recebidas[-1])[0].find("n:serv/n:cServ", NS)
    assert cs.find("n:cTribNac", NS).text == "171901" and cs.find("n:cNBS", NS).text == "113022100"

    # códigos inválidos e nota sem serviço nenhum são recusados antes do envio
    ruim = _sem_servico(e)
    ruim["servico"] = {**CODIGOS, "ctribnac": "999999"}
    assert cliente.post("/api/emissor/notas", json=ruim).status_code == 422
    nada = _sem_servico(e)
    nada.pop("servico")
    assert cliente.post("/api/emissor/notas", json=nada).status_code == 422
    sem_descricao = _sem_servico(e, descricao=" ")
    assert cliente.post("/api/emissor/notas", json=sem_descricao).status_code == 422
    assert len(sefin.recebidas) == 1

    # rascunho e recorrência guardam os códigos
    dados = {k: v for k, v in _sem_servico(e).items() if k not in ("empresa_id", "competencia")}
    rasc = cliente.post("/api/emissor/rascunhos", json={"empresa_id": e["id"], "dados": dados}).json()
    assert rasc["dados"]["servico"]["ctribnac"] == "171901"


def _nota_adn(empresa_id: int, d, numero="35") -> int:
    rel = f"empresas/teste/prestadas/NFSe_{numero}.xml"
    arq = config().dados_dir / rel
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(serializar(montar(d)))
    with nova_sessao() as db:
        n = Nota(empresa_id=empresa_id, chave=numero.rjust(44, "9"), papel="prestada", status="autorizada", numero=numero,
                 xml_path=rel, data_emissao=datetime(2026, 11, 9, 10, 0, tzinfo=BRASILIA))
        db.add(n)
        db.commit()
        return n.id


def test_ultima_nota_preenche_prestador_e_servico(cliente, sefin):
    e, s = _pronta(cliente)
    url = f"/api/emissor/empresas/{e['id']}/ultima-nota"
    assert cliente.get(url).json() is None  # sem nota do ADN

    d = _dados(op="3", ap="2")
    d.ctribmun = "001"
    nid = _nota_adn(e["id"], d)
    r = cliente.get(url).json()
    assert r["numero_nfse"] == "35" and r["emitida_pelo_contask"] is False and r["data"].startswith("2026-11-09")
    assert r["prestador"] == {"inscricao_municipal": "12345", "op_simples": "3", "reg_ap_trib_sn": "2", "reg_esp_trib": "0",
                              "cod_municipio": "5300108", "serie": "1", "numero_dps": 7}
    assert r["servico"]["ctribnac"] == "171901" and r["servico"]["ctribmun"] == "001"
    assert r["servico"]["ctribnac_formatado"] == "17.19.01" and r["servico"]["cnbs_descricao"]
    # o serviço cadastrado não tem o código municipal 001: não é o mesmo
    assert r["servico_cadastrado"] is False

    m = cliente.get(f"/api/emissor/empresas/{e['id']}/notas/adn/{nid}/modelo").json()
    assert m["servico_id"] is None and m["ctribmun"] == "001" and m["ctribnac_descricao"]

    # com os mesmos códigos, o serviço cadastrado é reconhecido
    d2 = _dados()
    nid2 = _nota_adn(e["id"], d2, numero="36")
    assert cliente.get(url).json()["servico_cadastrado"] is True
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/notas/adn/{nid2}/modelo").json()["servico_id"] == s["id"]
