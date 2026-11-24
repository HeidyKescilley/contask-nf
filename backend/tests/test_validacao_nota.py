"""Validar a nota antes de transmitir: nada vai à Sefin, nenhum número é reservado, a nota segue rascunho."""
import httpx
import pytest

from app.emissor import parametros
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401 (fixture)


@pytest.fixture()
def adn_param(monkeypatch):
    """API de parâmetros municipais simulada: convênio e alíquota configuráveis por teste."""
    estado = {"aderente": 1, "aliquota": 200, "falhar": False, "chamadas": []}

    def responder(req: httpx.Request) -> httpx.Response:
        if estado["falhar"]:
            raise httpx.ConnectError("sem rede", request=req)
        estado["chamadas"].append(req.url.path)
        if req.url.path.endswith("/convenio"):
            return httpx.Response(200, json={"parametrosConvenio": {"aderenteEmissorNacional": estado["aderente"],
                                                                     "aderenteAmbienteNacional": 1}, "mensagem": "ok"})
        codigo = req.url.path.split("/")[-3]
        if estado["aliquota"] == 404:
            return httpx.Response(404, json={"aliquotas": None, "mensagem": "Alíquotas não encontradas."})
        return httpx.Response(200, json={"aliquotas": {codigo: [{"Incidencia": "SIM", "Aliq": 2.0, "DtIni": "2025-05-01T00:00:00"}]}})

    parametros._cache.clear()
    monkeypatch.setattr(parametros, "fabrica",
                        lambda pfx, senha: parametros.ClienteParametros(transport=httpx.MockTransport(responder),
                                                                        base_url="https://adn.simulado/parametrizacao"))
    return estado


def _itens(r):
    return {i["id"]: i for i in r["itens"]}


def test_nota_pronta_sem_enviar_nem_numerar(cliente, sefin, adn_param):
    e, s = _pronta(cliente)
    antes = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"]
    r = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s))
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["pronta"] is True and v["erros"] == 0
    it = _itens(v)
    assert it["empresa"]["situacao"] == "ok" and it["xml"]["situacao"] == "ok" and it["convenio"]["situacao"] == "ok"
    assert it["aliquota"]["situacao"] == "ok" and "2,00%" in it["aliquota"]["detalhe"] and "17.19.01.000" in it["aliquota"]["detalhe"]
    assert sefin.recebidas == [] and cliente.get("/api/emissor/notas").json() == []
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == antes
    assert any(c.endswith("/17.19.01.000/2026-11-09/aliquota") for c in adn_param["chamadas"])


def test_aliquota_nao_publicada_e_alerta_e_sem_convenio_e_erro(cliente, sefin, adn_param):
    e, s = _pronta(cliente)
    adn_param["aliquota"] = 404
    v = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s)).json()
    assert v["pronta"] is True and v["alertas"] == 1 and _itens(v)["aliquota"]["situacao"] == "alerta"
    parametros._cache.clear()
    adn_param["aderente"] = 0
    v = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s)).json()
    assert v["pronta"] is False and _itens(v)["convenio"]["situacao"] == "erro"


def test_sem_rede_vira_alerta_e_erro_de_regra_bloqueia(cliente, sefin, adn_param):
    e, s = _pronta(cliente)
    adn_param["falhar"] = True
    v = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s)).json()
    assert v["pronta"] is True and _itens(v)["convenio"]["situacao"] == "alerta"
    # regra da NFS-e: competência no futuro
    v = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s, competencia="2099-01-01")).json()
    assert v["pronta"] is False and "E0015" in _itens(v)["xml"]["detalhe"]
    assert sefin.recebidas == []


def test_municipio_da_receita_diferente_e_alerta(cliente, sefin, adn_param):
    e, s = _pronta(cliente)
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={"op_simples": "3", "reg_ap_trib_sn": "1", "cod_municipio": "3550308"})
    assert r.status_code == 200, r.text
    v = cliente.post("/api/emissor/notas/validar", json=_emissao(e, s)).json()
    assert _itens(v)["municipio"]["situacao"] == "alerta" and "E0084" in _itens(v)["municipio"]["detalhe"]


def test_codigo_de_servico_formatado():
    assert parametros.codigo_servico("040101", None) == "04.01.01.000"
    assert parametros.codigo_servico("170601", "001") == "17.06.01.001"
    assert parametros.codigo_servico("170601", "1602") == "17.06.01.000"  # código do DF (até 10 dígitos) não entra


def test_validacao_fica_no_rascunho_e_some_quando_ele_muda(cliente, sefin, adn_param):
    e, s = _pronta(cliente)
    corpo = _emissao(e, s)
    dados = {k: v for k, v in corpo.items() if k != "empresa_id"}
    r = cliente.post("/api/emissor/rascunhos", json={"empresa_id": e["id"], "dados": dados}).json()
    v = cliente.post("/api/emissor/notas/validar", json={**corpo, "rascunho_id": r["id"]}).json()
    assert v["pronta"] is True
    salvo = cliente.get(f"/api/emissor/rascunhos/{r['id']}").json()
    assert salvo["validacao"]["pronta"] is True and salvo["validacao"]["em"]
    # salvar igual mantém; mudar apaga
    cliente.put(f"/api/emissor/rascunhos/{r['id']}", json={"empresa_id": e["id"], "dados": dados})
    assert cliente.get(f"/api/emissor/rascunhos/{r['id']}").json()["validacao"] is not None
    cliente.put(f"/api/emissor/rascunhos/{r['id']}", json={"empresa_id": e["id"], "dados": {**dados, "valor": "2000.00"}})
    assert cliente.get(f"/api/emissor/rascunhos/{r['id']}").json()["validacao"] is None
    assert sefin.recebidas == []
