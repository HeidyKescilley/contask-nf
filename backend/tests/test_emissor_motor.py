"""Motor de emissão: DPS (dois leiautes), assinatura, numeração, Sefin simulada, recuperação e cancelamento."""
import base64
import gzip
import json
from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest
from lxml import etree

from app.emissor import assinatura, motor
from app.emissor.dps import (
    BRASILIA, PRODUCAO, RESTRITA, Cancelamento, DadosDps, DpsInvalida, Prestador, Retencoes, TomadorDps, montar,
    montar_cancelamento, precisa_aliquota, validar_xsd,
)
from app.emissor.sefin import ClienteSefin
from tests.adn_simulado import evento_xml, nfse_xml
from tests.certs import criar_pfx, dv_cnpj
from tests.test_emissor_cadastros import OUTRO, _empresa_propria
from tests.test_empresas import CLIENTE, SENHA, _contabilidade

NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}
CHAVE = f"530010822{OUTRO}" + "0" * 26 + "1"  # município(7) + ambiente(1) + tipo inscrição(1) + CNPJ + ...


def _dados(amb=RESTRITA, op="3", ap="1", retencoes=None, tomador=True, aliquota=None):
    return DadosDps(
        ambiente=amb, serie="1", numero=7, competencia=date(2026, 11, 9),
        prestador=Prestador(cnpj=OUTRO, cod_municipio="5300108", op_simples=op, reg_ap_trib_sn=ap if op == "3" else None,
                            reg_esp_trib="0", inscricao_municipal="12345"),
        tomador=TomadorDps(documento=CLIENTE, nome="Tomador Teste Ltda", cep="70040010", cod_municipio="5300108",
                           logradouro="SBS Quadra 2", numero="10", bairro="Asa Sul", email="a@b.com") if tomador else None,
        ctribnac="171901", cnbs="113022100", descricao="Honorários contábeis", valor=Decimal("1000.00"),
        cod_municipio_prestacao="5300108", retencoes=retencoes or Retencoes(), aliquota_iss=aliquota,
        percentual_tributos_sn=Decimal("6.00"), emitido_em=datetime(2026, 11, 9, 10, 0, tzinfo=BRASILIA),
    )


def _assinada(d):
    raiz = montar(d)
    chave, cert = assinatura.carregar_chave(criar_pfx("EMPRESA PROPRIA LTDA", cnpj=OUTRO), SENHA)
    assinatura.assinar(raiz, raiz[0], chave, cert)
    return raiz


@pytest.mark.parametrize("amb", [RESTRITA, PRODUCAO])
def test_dps_valida_no_xsd_dos_dois_ambientes(amb):
    raiz = _assinada(_dados(amb))
    validar_xsd(raiz, amb)
    assert assinatura.conferir(raiz)
    inf = raiz[0]
    assert inf.get("Id") == f"DPS53001082{OUTRO}00001000000000000007"
    nomes = [etree.QName(e).localname for e in inf.find("n:serv/n:cServ", NS)]
    if amb == RESTRITA:
        assert inf.find("n:finNFSe", NS) is not None and nomes == ["cTribNac", "cNBS", "xDescServ"]
    else:
        assert inf.find("n:finNFSe", NS) is None and nomes == ["cTribNac", "xDescServ", "cNBS"]
    assert inf.find("n:prest/n:xNome", NS) is None  # E0121
    assert inf.find("n:valores/n:trib/n:totTrib/n:pTotTribSN", NS).text == "6.00"  # E0712


def test_assinatura_usa_canonicalizacao_exclusiva():
    raiz = _assinada(_dados())
    sig = raiz.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
    algs = [e.get("Algorithm") for e in sig.iter() if e.get("Algorithm")]
    assert algs.count("http://www.w3.org/2001/10/xml-exc-c14n#") == 2
    raiz[0].find("n:serv/n:cServ/n:xDescServ", NS).text = "alterado"
    assert not assinatura.conferir(raiz)


def test_nao_optante_usa_indicador_de_tributos():
    inf = montar(_dados(op="1"))[0]
    assert inf.find("n:valores/n:trib/n:totTrib/n:indTotTrib", NS).text == "0"
    assert inf.find("n:prest/n:regTrib/n:regApTribSN", NS) is None


def test_aliquota_so_quando_simples_com_iss_retido():
    p = Prestador(cnpj=OUTRO, cod_municipio="5300108", op_simples="3", reg_ap_trib_sn="1", reg_esp_trib="0")
    assert precisa_aliquota(p, True) and not precisa_aliquota(p, False)
    assert not precisa_aliquota(Prestador(OUTRO, "5300108", "1", None, "0"), True)
    with pytest.raises(DpsInvalida, match="alíquota"):
        montar(_dados(retencoes=Retencoes(iss=True)))
    inf = montar(_dados(retencoes=Retencoes(iss=True), aliquota=Decimal("2.5")))[0]
    assert inf.find("n:valores/n:trib/n:tribMun/n:pAliq", NS).text == "2.50"
    assert inf.find("n:valores/n:trib/n:tribMun/n:tpRetISSQN", NS).text == "2"
    assert montar(_dados())[0].find("n:valores/n:trib/n:tribMun/n:pAliq", NS) is None
    sem_end = _dados(retencoes=Retencoes(iss=True), aliquota=Decimal("2"))
    sem_end.tomador = TomadorDps(documento=CLIENTE, nome="Sem endereço")
    with pytest.raises(DpsInvalida, match="E0237"):
        montar(sem_end)


def test_retencoes_federais():
    r = Retencoes(pis=Decimal("6.50"), cofins=Decimal("30.00"), csll=Decimal("10.00"), irrf=Decimal("15.00"), cp=Decimal("110.00"))
    raiz = _assinada(_dados(op="1", retencoes=r))
    validar_xsd(raiz, RESTRITA)
    tf = raiz[0].find("n:valores/n:trib/n:tribFed", NS)
    assert tf.find("n:piscofins/n:tpRetPisCofins", NS).text == "3"
    assert tf.find("n:vRetCSLL", NS).text == "46.50"  # PIS + COFINS + CSLL
    assert tf.find("n:vRetIRRF", NS).text == "15.00" and tf.find("n:vRetCP", NS).text == "110.00"
    assert Retencoes(pis=Decimal(1), cofins=Decimal(1)).tp_ret_pis_cofins == "4"
    assert Retencoes(csll=Decimal(1)).tp_ret_pis_cofins == "8"
    with pytest.raises(DpsInvalida, match="MEI"):
        montar(_dados(op="2", retencoes=Retencoes(irrf=Decimal(1))))
    with pytest.raises(DpsInvalida, match="não podem chegar"):
        montar(_dados(op="1", retencoes=Retencoes(irrf=Decimal("600"), cp=Decimal("400"))))


def test_tomador_sem_endereco_e_sem_tomador():
    d = _dados()
    d.tomador = TomadorDps(documento="52998224725", nome="Pessoa Física")
    inf = montar(d)[0]
    assert inf.find("n:toma/n:CPF", NS).text == "52998224725" and inf.find("n:toma/n:end", NS) is None
    validar_xsd(_assinada(_dados(tomador=False)), RESTRITA)


def test_cancelamento_valida_no_xsd():
    c = Cancelamento(ambiente=RESTRITA, cnpj_autor=OUTRO, chave=CHAVE, motivo="1", justificativa="Erro no valor do serviço")
    raiz = montar_cancelamento(c)
    chave, cert = assinatura.carregar_chave(criar_pfx("EMPRESA PROPRIA LTDA", cnpj=OUTRO), SENHA)
    assinatura.assinar(raiz, raiz[0], chave, cert)
    validar_xsd(raiz, RESTRITA, "pedRegEvento_v1.01.xsd")
    assert raiz[0].get("Id") == "PRE" + CHAVE + "101101"
    with pytest.raises(DpsInvalida, match="15 a 255"):
        montar_cancelamento(Cancelamento(RESTRITA, OUTRO, CHAVE, "1", "curta"))


# ---------------------------------------------------------------------------
# Sefin simulada
# ---------------------------------------------------------------------------

class SefinSimulada:
    def __init__(self):
        self.notas: dict[str, str] = {}  # id_dps -> chave
        self.modo = "ok"  # ok | rejeita | cai_depois | cai_antes
        self.recebidas: list[bytes] = []
        self.eventos = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path.endswith("/nfse"):
            xml = gzip.decompress(base64.b64decode(json.loads(req.content)["dpsXmlGZipB64"]))
            self.recebidas.append(xml)
            raiz = etree.fromstring(xml)
            assert assinatura.conferir(raiz)
            inf = raiz[0]
            id_dps = inf.get("Id")
            if self.modo == "cai_antes":
                raise httpx.ConnectError("sem rede")
            if self.modo == "rejeita":
                return httpx.Response(400, json={"erros": [{"Codigo": "E0160", "Descricao": "Simples divergente."}]})
            if id_dps in self.notas:
                return httpx.Response(400, json={"erros": [{"Codigo": "E0014", "Descricao": "DPS já gerou NFS-e."}]})
            prest = inf.find("n:prest/n:CNPJ", NS).text
            chave = f"530010822{prest}{len(self.notas) + 1:027d}"
            self.notas[id_dps] = chave
            if self.modo == "cai_depois":
                raise httpx.ReadTimeout("caiu")
            return httpx.Response(201, json={"chaveAcesso": chave, "nfseXmlGZipB64": self._nfse(chave, prest)})
        if req.method == "GET" and "/dps/" in req.url.path:
            chave = self.notas.get(req.url.path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"chaveAcesso": chave}) if chave else httpx.Response(404, json={"erro": {"codigo": "E404"}})
        if req.method == "GET" and "/nfse/" in req.url.path:
            chave = req.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"nfseXmlGZipB64": self._nfse(chave, OUTRO)})
        if req.method == "POST" and req.url.path.endswith("/eventos"):
            self.eventos += 1
            chave = req.url.path.split("/")[-2]
            return httpx.Response(201, json={"eventoXmlGZipB64": base64.b64encode(gzip.compress(evento_xml(chave, "101101"))).decode()})
        return httpx.Response(404)

    @staticmethod
    def _nfse(chave, prest):
        return base64.b64encode(gzip.compress(nfse_xml(chave, prest=prest, toma=CLIENTE, valor="1000.00", numero=42))).decode()


@pytest.fixture()
def sefin(monkeypatch):
    s = SefinSimulada()
    monkeypatch.setattr(motor, "fabrica_cliente",
                        lambda amb, pfx, senha: ClienteSefin(ambiente=amb, transport=httpx.MockTransport(s)))
    return s


def _pronta(cliente):
    assert _contabilidade(cliente).status_code == 200
    e = _empresa_propria(cliente, dados_brasilapi='{"opcao_pelo_simples": true, "codigo_municipio_ibge": 5300108}').json()["empresa"]
    cliente.put("/api/emissor/empresas/emissao", json={"empresa_ids": [e["id"]], "emite": True})
    s = cliente.post(f"/api/emissor/empresas/{e['id']}/servicos",
                     json={"descricao": "Honorários contábeis", "ctribnac": "171901", "cnbs": "113022100"}).json()
    return e, s


def _emissao(e, s, **extra):
    return {"empresa_id": e["id"], "servico_id": s["id"], "competencia": "2026-11-09", "valor": "1000.00",
            "tomador": {"documento": CLIENTE, "nome": "Tomador Teste Ltda"}, **extra}


def test_emissao_autorizada(cliente, sefin):
    e, s = _pronta(cliente)
    assert cliente.get("/api/emissor/ambiente").json()["producao"] is False
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s))
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["situacao"] == "autorizada" and n["numero"] == 1 and n["homologacao"]
    assert n["chave"] and n["numero_nfse"] == "42" and n["valor_liquido"] == 1000.0
    # tpAmb=2 na DPS enviada (produção restrita)
    assert etree.fromstring(sefin.recebidas[0])[0].find("n:tpAmb", NS).text == "2"
    # numeração avança; tomador fica salvo
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == 2
    assert cliente.get("/api/emissor/tomadores").json()[0]["documento"] == CLIENTE
    assert cliente.get(f"/api/emissor/notas/{n['id']}/xml").status_code == 200
    assert cliente.get(f"/api/emissor/notas/{n['id']}/danfse").headers["content-type"] == "application/pdf"
    n2 = cliente.post("/api/emissor/notas", json=_emissao(e, s, descricao="Outro serviço")).json()
    assert n2["numero"] == 2 and n2["descricao"] == "Outro serviço"
    assert [x["id"] for x in cliente.get("/api/emissor/notas", params={"empresa_id": e["id"]}).json()] == [n2["id"], n["id"]]


def test_erro_de_validacao_nao_gasta_numero(cliente, sefin):
    e, s = _pronta(cliente)
    r = cliente.post("/api/emissor/notas", json=_emissao(e, s, iss_retido=True))  # Simples com ISS retido sem alíquota
    assert r.status_code == 422 and "alíquota" in r.json()["detail"]
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == 1
    assert sefin.recebidas == []


def test_rejeitada_e_reenviada_com_o_mesmo_numero(cliente, sefin):
    e, s = _pronta(cliente)
    sefin.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "rejeitada" and n["erros"][0]["codigo"] == "E0160"
    sefin.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n['id']}/reenviar", json=_emissao(e, s, valor="900.00"))
    assert r.json()["situacao"] == "autorizada" and r.json()["numero"] == n["numero"] and r.json()["valor_servico"] == 900.0
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == 2


def test_queda_depois_do_envio_recupera_sem_duplicar(cliente, sefin):
    e, s = _pronta(cliente)
    sefin.modo = "cai_depois"  # a Sefin gerou a nota, mas a resposta se perdeu
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "autorizada" and len(sefin.notas) == 1


def test_queda_antes_fica_pendente_e_reenvia(cliente, sefin):
    e, s = _pronta(cliente)
    sefin.modo = "cai_antes"
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert n["situacao"] == "pendente" and "pode reenviar" in n["mensagem"]
    sefin.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n['id']}/reenviar").json()
    assert r["situacao"] == "autorizada" and len(sefin.notas) == 1


def test_cancelamento(cliente, sefin):
    e, s = _pronta(cliente)
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    assert cliente.post(f"/api/emissor/notas/{n['id']}/cancelar", json={"motivo": "1", "justificativa": "curta"}).status_code == 422
    r = cliente.post(f"/api/emissor/notas/{n['id']}/cancelar", json={"motivo": "1", "justificativa": "Valor informado errado na nota"})
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "cancelada" and sefin.eventos == 1
    assert cliente.post(f"/api/emissor/notas/{n['id']}/cancelar", json={"motivo": "1", "justificativa": "Valor informado errado na nota"}).status_code == 409


def test_bloqueios(cliente, sefin):
    assert _contabilidade(cliente).status_code == 200
    proc = cliente.post("/api/empresas", data={"cnpj": CLIENTE, "razao_social": "Cliente", "modo_certificado": "contabilidade",
                                               "emite_nfse": "true"}).json()["empresa"]
    s = cliente.post(f"/api/emissor/empresas/{proc['id']}/servicos",
                     json={"descricao": "X", "ctribnac": "171901", "cnbs": "113022100"}).json()
    r = cliente.post("/api/emissor/notas", json=_emissao(proc, s))
    assert r.status_code == 422 and "procuração não serve" in r.json()["detail"]
    cliente.put("/api/emissor/empresas/emissao", json={"empresa_ids": [proc["id"]], "emite": False})
    assert "não está marcada" in cliente.post("/api/emissor/notas", json=_emissao(proc, s)).json()["detail"]
    assert sefin.recebidas == []


def test_producao_so_com_liberacao(cliente, sefin, monkeypatch):
    from app.core import config as cfgmod
    e, s = _pronta(cliente)
    monkeypatch.setenv("CONTASK_EMISSOR_PRODUCAO", "true")
    cfgmod.config.cache_clear()
    try:
        assert cliente.get("/api/emissor/ambiente").json()["producao"] is True
        cliente.post("/api/emissor/notas", json=_emissao(e, s))
        assert etree.fromstring(sefin.recebidas[-1])[0].find("n:tpAmb", NS).text == "1"
    finally:
        monkeypatch.delenv("CONTASK_EMISSOR_PRODUCAO")
        cfgmod.config.cache_clear()
