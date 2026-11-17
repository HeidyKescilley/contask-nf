"""Troca do leiaute da DPS em produção (NT 004 -> NT 009): escolha por configuração e troca automática no E1235."""
import pytest
from lxml import etree

from app.core import config as cfgmod
from app.emissor import motor
from app.emissor.dps import (
    ARQUIVO_LEIAUTE, NT004, NT009, PRODUCAO, RESTRITA, gravar_leiaute_producao, leiaute_do_ambiente, montar,
    validar_xsd,
)
from tests.test_emissor_ibscbs import _regular
from tests.test_emissor_motor import NS, _assinada, _dados, _emissao, _pronta, sefin  # noqa: F401


def test_escolha_do_leiaute(app_teste, monkeypatch):
    assert leiaute_do_ambiente(RESTRITA) == NT009
    assert leiaute_do_ambiente(PRODUCAO) == NT004
    monkeypatch.setenv("CONTASK_LEIAUTE_PRODUCAO", "nt009")
    cfgmod.config.cache_clear()
    assert leiaute_do_ambiente(PRODUCAO) == NT009
    gravar_leiaute_producao(NT004)  # o que a Sefin aceitou por último vale mais que a configuração
    assert leiaute_do_ambiente(PRODUCAO) == NT004
    (cfgmod.config().dados_dir / ARQUIVO_LEIAUTE).write_text("lixo")
    assert leiaute_do_ambiente(PRODUCAO) == NT009


@pytest.mark.parametrize("d", [_dados(PRODUCAO), _regular(PRODUCAO), _regular(PRODUCAO, cclasstrib="410001")])
def test_producao_no_leiaute_nt009(app_teste, monkeypatch, d):
    monkeypatch.setenv("CONTASK_LEIAUTE_PRODUCAO", "nt009")
    cfgmod.config.cache_clear()
    raiz = _assinada(d)
    validar_xsd(raiz, PRODUCAO)
    inf = raiz[0]
    assert inf.find("n:tpAmb", NS).text == "1"
    assert inf.find("n:finNFSe", NS) is not None
    assert [c.tag.split("}")[1] for c in inf.find("n:serv/n:cServ", NS)][-2:] == ["cNBS", "xDescServ"]
    with pytest.raises(Exception):
        validar_xsd(raiz, PRODUCAO, leiaute=NT004)


def _producao(cliente, monkeypatch):
    e, s = _pronta(cliente)
    monkeypatch.setenv("CONTASK_EMISSOR_PRODUCAO", "true")
    cfgmod.config.cache_clear()
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["ambiente"] == 1
    return e, s


def _leiaute_enviado(xml: bytes) -> str:
    return NT009 if etree.fromstring(xml)[0].find("n:finNFSe", NS) is not None else NT004


def test_producao_troca_sozinha_quando_a_sefin_recusa_o_esquema(cliente, sefin, monkeypatch):
    e, s = _producao(cliente, monkeypatch)
    sefin.leiaute_producao = NT009  # a Sefin de produção já trocou de leiaute
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s))
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["situacao"] == "autorizada" and n["numero"] == 1
    assert [_leiaute_enviado(x) for x in sefin.recebidas] == [NT004, NT009]
    assert leiaute_do_ambiente(PRODUCAO) == NT009  # gravado para as próximas
    # o XML guardado da DPS é o que foi aceito
    from app.models import NotaEmitida
    from app.core.db import nova_sessao
    with nova_sessao() as db:
        caminho = db.get(NotaEmitida, n["id"]).xml_dps_path
    assert _leiaute_enviado((cfgmod.config().dados_dir / caminho).read_bytes()) == NT009
    # a próxima já vai direto no leiaute novo
    n2 = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n2["situacao"] == "autorizada" and n2["numero"] == 2
    assert [_leiaute_enviado(x) for x in sefin.recebidas] == [NT004, NT009, NT009]


def test_producao_sem_troca_quando_o_leiaute_confere(cliente, sefin, monkeypatch):
    e, s = _producao(cliente, monkeypatch)
    sefin.leiaute_producao = NT004
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "autorizada"
    assert [_leiaute_enviado(x) for x in sefin.recebidas] == [NT004]
    assert not (cfgmod.config().dados_dir / ARQUIVO_LEIAUTE).exists()


def test_rejeicao_de_negocio_nao_troca_leiaute(cliente, sefin, monkeypatch):
    e, s = _producao(cliente, monkeypatch)
    sefin.modo = "rejeita"  # E0160: não é esquema
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "rejeitada" and "E0160" in n["mensagem"]
    assert len(sefin.recebidas) == 1
    assert leiaute_do_ambiente(PRODUCAO) == NT004


def test_esquema_recusado_nos_dois_leiautes_fica_rejeitada(cliente, sefin, monkeypatch):
    e, s = _producao(cliente, monkeypatch)
    monkeypatch.setattr(motor, "erro_de_esquema", lambda erros: True)
    sefin.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "rejeitada"
    assert [_leiaute_enviado(x) for x in sefin.recebidas] == [NT004, NT009]
    assert leiaute_do_ambiente(PRODUCAO) == NT004


def test_homologacao_nunca_troca(cliente, sefin):
    e, s = _pronta(cliente)
    sefin.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "rejeitada" and len(sefin.recebidas) == 1
    assert _leiaute_enviado(sefin.recebidas[0]) == NT009
