"""Teste grátis por escritório: XML avulso fechado, PDF só para ver, uma exportação curta e uma emissão."""
from app.core.db import nova_sessao
from app.models import Escritorio
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401 (fixture)


def _em_teste(cliente):
    esc = cliente.get("/api/auth/eu").json()["escritorio"]["id"]
    with nova_sessao() as db:
        db.get(Escritorio, esc).situacao = "teste"
        db.commit()
    return esc


def test_teste_fecha_xml_e_libera_uma_emissao(cliente, sefin):
    e, s = _pronta(cliente)
    _em_teste(cliente)
    uso = cliente.get("/api/uso").json()
    assert uso["situacao"] == "teste" and uso["teste"]["max_emissoes"] == 1 and uso["teste"]["emissoes"] == 0

    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "autorizada"
    assert cliente.get("/api/uso").json()["teste"]["emissoes"] == 1
    # PDF abre para ver; download do PDF e do XML ficam fechados
    assert cliente.get(f"/api/emissor/notas/{n['id']}/danfse").status_code == 200
    assert cliente.get(f"/api/emissor/notas/{n['id']}/danfse?download=1").status_code == 402
    r = cliente.get(f"/api/emissor/notas/{n['id']}/xml")
    assert r.status_code == 402 and "plano" in r.json()["detail"]
    # Segunda emissão bloqueada, sem gastar número
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s))
    assert r.status_code == 402 and "teste grátis" in r.json()["detail"]
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == 2
    # Recorrência fechada
    rec = {"empresa_id": e["id"], "nome": "Mensal", "dia": 5, "dados": {k: v for k, v in _emissao(e, s).items()
                                                                     if k not in ("empresa_id", "competencia")}}
    assert cliente.post("/api/emissor/recorrentes", json=rec).status_code == 402


def test_teste_permite_reenviar_a_nota_rejeitada(cliente, sefin):
    e, s = _pronta(cliente)
    _em_teste(cliente)
    sefin.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "rejeitada"
    sefin.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n['id']}/reenviar", json=_emissao(e, s))
    assert r.status_code == 200 and r.json()["situacao"] == "autorizada"


def test_plano_ativo_libera_tudo(cliente, sefin):
    e, s = _pronta(cliente)
    n1 = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    n2 = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n1["situacao"] == n2["situacao"] == "autorizada"
    assert cliente.get(f"/api/emissor/notas/{n1['id']}/xml").status_code == 200
    assert cliente.get(f"/api/emissor/notas/{n1['id']}/danfse?download=1").status_code == 200


def test_empresa_emissora_nova_comeca_em_producao(cliente, sefin):
    e, _s = _pronta(cliente)
    cfg = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]
    assert cfg["producao_liberada"] is True
