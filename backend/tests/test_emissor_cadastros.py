"""Emissor: empresas emissoras, dados do prestador, serviços, tabelas oficiais e tomadores."""
import httpx

from app.core import brasilapi
from app.emissor import tabelas
from tests.certs import criar_pfx, dv_cnpj
from tests.test_empresas import CLIENTE, CONTAB, SENHA, _contabilidade, _empresa, _pfx

OUTRO = dv_cnpj("223334440001")


def _empresa_propria(cliente, cnpj=OUTRO, **extra):
    pfx = criar_pfx("EMPRESA PROPRIA LTDA", cnpj=cnpj)
    return _empresa(cliente, cnpj=cnpj, modo_certificado="proprio", senha=SENHA,
                    files={"arquivo": ("e.pfx", pfx, "application/x-pkcs12")}, **extra)


def _preparar(cliente):
    assert _contabilidade(cliente).status_code == 200
    proc = _empresa(cliente).json()["empresa"]  # por procuração
    prop = _empresa_propria(cliente).json()["empresa"]  # certificado próprio
    return proc, prop


def test_tabelas_oficiais():
    assert tabelas.servico("171901")["item"] == "17.19"
    assert tabelas.nbs_descricao("113022100") == "Serviços de contabilidade"
    assert any(s["nbs"] == "113022100" and s["cclasstrib"] for s in tabelas.sugestoes("171901"))
    assert tabelas.buscar_servicos("17.19")[0]["codigo"] == "171901"
    assert tabelas.buscar_servicos("contabilidade")[0]["codigo"] == "171901"
    assert tabelas.formatar_nbs("113022100") == "1.1302.21.00"


def test_marcar_em_lote_e_pendencias(cliente):
    proc, prop = _preparar(cliente)
    lista = cliente.get("/api/emissor/empresas").json()
    assert {e["id"]: e["emite_nfse"] for e in lista}[prop["id"]] is False

    r = cliente.put("/api/emissor/empresas/emissao", json={"empresa_ids": [proc["id"], prop["id"]], "emite": True})
    assert r.json() == {"atualizadas": 2}
    itens = {e["id"]: e for e in cliente.get("/api/emissor/empresas").json()}
    assert itens[proc["id"]]["emite_nfse"] and itens[prop["id"]]["emite_nfse"]
    # por procuração: usa o certificado da contabilidade, mas a homologação recusa (E0718)
    assert itens[proc["id"]]["certificado"]["procuracao"] is True
    assert any("E0718" in p for p in itens[proc["id"]]["pendencias"])
    assert any("cancelamento por procuração" in a for a in itens[proc["id"]]["avisos"])
    assert itens[prop["id"]]["certificado"]["procuracao"] is False and itens[prop["id"]]["avisos"] == []
    assert itens[prop["id"]]["certificado"]["titular_doc"] == OUTRO
    assert itens[prop["id"]]["pendencias"] == ["Cadastre pelo menos um serviço.",
                                               "Não foi possível descobrir o código IBGE do município da empresa. "
                                               "Confira o município e a UF no cadastro da empresa ou informe o código "
                                               "nos dados do prestador."]
    assert not itens[prop["id"]]["pronta"]
    assert itens[prop["id"]]["config"]["serie"] == "1" and itens[prop["id"]]["config"]["proximo_numero"] == 1

    cliente.put("/api/emissor/empresas/emissao", json={"empresa_ids": [proc["id"]], "emite": False})
    assert cliente.get(f"/api/empresas/{proc['id']}").json()["emite_nfse"] is False
    assert cliente.put("/api/emissor/empresas/emissao", json={"empresa_ids": [999], "emite": True}).status_code == 404


def test_opcao_no_cadastro_e_na_edicao(cliente):
    assert _contabilidade(cliente).status_code == 200
    r = _empresa(cliente, emite_nfse="true")
    assert r.json()["empresa"]["emite_nfse"] is True
    assert any("certificado A1 da própria empresa" in a for a in r.json()["avisos"])
    eid = r.json()["empresa"]["id"]
    assert cliente.patch(f"/api/empresas/{eid}", json={"emite_nfse": False}).json()["emite_nfse"] is False


def test_regime_inicial_vem_do_simples(cliente, monkeypatch):
    assert _contabilidade(cliente).status_code == 200
    r = _empresa_propria(cliente, dados_brasilapi='{"opcao_pelo_simples": true, "opcao_pelo_mei": false}')
    cfg = cliente.get(f"/api/emissor/empresas/{r.json()['empresa']['id']}").json()["config"]
    assert cfg["op_simples"] == "3" and cfg["reg_ap_trib_sn"] == "1"


def test_config_do_prestador_validada(cliente):
    _, prop = _preparar(cliente)
    url = f"/api/emissor/empresas/{prop['id']}/config"
    ok = {"inscricao_municipal": " 0745217800 ", "op_simples": "3", "reg_ap_trib_sn": "1", "reg_esp_trib": "0",
          "serie": "00002", "proximo_numero": 15}
    d = cliente.put(url, json=ok).json()["config"]
    assert d["serie"] == "2" and d["proximo_numero"] == 15 and d["inscricao_municipal"] == "0745217800"
    assert cliente.put(url, json={**ok, "reg_ap_trib_sn": None}).status_code == 422  # ME/EPP sem regime
    assert cliente.put(url, json={**ok, "op_simples": "1"}).status_code == 422       # regime SN para não optante
    assert cliente.put(url, json={**ok, "serie": "50000"}).status_code == 422        # faixa do emissor móvel
    assert cliente.put(url, json={**ok, "proximo_numero": 0}).status_code == 422


def test_servicos_da_empresa(cliente):
    _, prop = _preparar(cliente)
    base = f"/api/emissor/empresas/{prop['id']}/servicos"
    s = {"descricao": "Honorários contábeis", "ctribnac": "17.19.01", "cnbs": "1.1302.21.00", "ctribmun": ""}
    r = cliente.post(base, json=s)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ctribnac"] == "171901" and d["cnbs"] == "113022100" and d["ctribmun"] is None
    assert d["ctribnac_formatado"] == "17.19.01" and d["cnbs_descricao"] == "Serviços de contabilidade"
    assert cliente.post(base, json={**s, "ctribnac": "999999"}).status_code == 422
    assert cliente.post(base, json={**s, "cnbs": "123"}).status_code == 422
    assert cliente.post(base, json={**s, "descricao": "  "}).status_code == 422
    assert cliente.post(base, json={**s, "ctribmun": "12"}).status_code == 422

    item = {e["id"]: e for e in cliente.get("/api/emissor/empresas").json()}[prop["id"]]
    assert item["servicos"] == 1

    r = cliente.put(f"/api/emissor/servicos/{d['id']}", json={**s, "descricao": "Escrituração", "ativo": False})
    assert r.json()["descricao"] == "Escrituração" and r.json()["ativo"] is False
    assert cliente.get(base).json() == []
    assert len(cliente.get(base, params={"inativos": True}).json()) == 1
    assert cliente.delete(f"/api/emissor/servicos/{d['id']}").status_code == 204
    assert cliente.get(base, params={"inativos": True}).json() == []


def test_codigos_e_sugestoes(cliente):
    _preparar(cliente)
    assert cliente.get("/api/emissor/codigos/servicos", params={"q": "contabil"}).json()[0]["codigo_formatado"] == "17.19.01"
    assert cliente.get("/api/emissor/codigos/nbs", params={"q": "1.1302.21"}).json()[0]["codigo"] == "113022100"
    sug = cliente.get("/api/emissor/codigos/sugestoes/17.19.01").json()
    assert sug[0]["nbs_formatado"].startswith("1.1302")


def test_tomadores(cliente, monkeypatch):
    _preparar(cliente)
    bruto = {"razao_social": "TOMADOR TESTE LTDA", "uf": "DF", "municipio": "BRASILIA", "codigo_municipio_ibge": 5300108,
             "cep": "71990-180", "descricao_tipo_de_logradouro": "RUA", "logradouro": "DAS FLORES", "numero": "",
             "complemento": "SALA 1", "bairro": "CENTRO", "ddd_telefone_1": "6130229700", "email": "FIN@TOMADOR.COM.BR",
             "descricao_situacao_cadastral": "ATIVA"}
    original = brasilapi.consultar
    monkeypatch.setattr(brasilapi, "consultar", lambda c: original(
        c, cliente=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=bruto)))))

    r = cliente.get(f"/api/emissor/tomadores/consulta/{CLIENTE}").json()
    assert r["origem"] == "brasilapi"
    t = r["tomador"]
    assert t["nome"] == "TOMADOR TESTE LTDA" and t["cod_municipio"] == "5300108" and t["cep"] == "71990180"
    assert t["logradouro"] == "RUA DAS FLORES" and t["numero"] == "S/N" and t["email"] == "fin@tomador.com.br"

    salvo = cliente.post("/api/emissor/tomadores", json=t)
    assert salvo.status_code == 201, salvo.text
    assert cliente.get(f"/api/emissor/tomadores/consulta/{CLIENTE}").json()["origem"] == "salvo"
    # salvar de novo o mesmo CNPJ atualiza, não duplica
    cliente.post("/api/emissor/tomadores", json={**t, "nome": "TOMADOR NOVO NOME"})
    lista = cliente.get("/api/emissor/tomadores").json()
    assert len(lista) == 1 and lista[0]["nome"] == "TOMADOR NOVO NOME"
    assert cliente.get("/api/emissor/tomadores", params={"q": "novo"}).json()[0]["documento"] == CLIENTE

    cpf = cliente.get("/api/emissor/tomadores/consulta/529.982.247-25").json()
    assert cpf["origem"] == "manual" and cpf["tomador"]["documento"] == "52998224725"
    assert cliente.get("/api/emissor/tomadores/consulta/123").status_code == 422
    assert cliente.post("/api/emissor/tomadores", json={"documento": CONTAB, "nome": "X", "cep": "71990180"}).status_code == 422
    assert cliente.post("/api/emissor/tomadores", json={"documento": CONTAB, "nome": "X", "email": "sem-arroba"}).status_code == 422
    assert cliente.delete(f"/api/emissor/tomadores/{lista[0]['id']}").status_code == 204


def test_isolamento_entre_escritorios(app_teste):
    from fastapi.testclient import TestClient
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as a, TestClient(app_teste, base_url="http://127.0.0.1:8765") as b:
        a.post("/api/auth/cadastrar", json={"nome": "A", "email": "a@x.com", "senha": "Senha-Forte-123"})
        b.post("/api/auth/cadastrar", json={"nome": "B", "email": "b@x.com", "senha": "Senha-Forte-123"})
        _, prop = _preparar(a)
        s = a.post(f"/api/emissor/empresas/{prop['id']}/servicos",
                   json={"descricao": "X", "ctribnac": "171901", "cnbs": "113022100"}).json()
        t = a.post("/api/emissor/tomadores", json={"documento": CLIENTE, "nome": "T"}).json()
        assert b.get(f"/api/emissor/empresas/{prop['id']}").status_code == 404
        assert b.get(f"/api/emissor/empresas/{prop['id']}/servicos").status_code == 404
        assert b.put(f"/api/emissor/servicos/{s['id']}", json={"descricao": "Y", "ctribnac": "171901", "cnbs": "113022100"}).status_code == 404
        assert b.delete(f"/api/emissor/tomadores/{t['id']}").status_code == 404
        assert b.get("/api/emissor/tomadores").json() == []
        assert b.put("/api/emissor/empresas/emissao", json={"empresa_ids": [prop["id"]], "emite": True}).status_code == 404


def test_municipio_ibge_pelo_nome_e_uf():
    from app.core import ibge
    assert ibge.normalizar("Santa Bárbara d'Oeste") == "SANTA BARBARA D OESTE"
    assert ibge.codigo("DF", "Brasília") == "5300108"
    assert ibge.codigo("df", "BRASILIA") == "5300108"
    assert ibge.codigo(None, "5300108") == "5300108"  # já digitado como código
    assert ibge.codigo("SP", "Cidade Inexistente") is None
    assert ibge.codigo("XX", "Brasília") is None


def test_garantir_municipio_preenche_o_prestador():
    from app.emissor.municipio import garantir_municipio
    from app.models import EmissorEmpresa, Empresa

    class Db:
        def commit(self):
            pass
    e = Empresa(cnpj="38030646000194", razao_social="X", uf="DF", municipio="Brasília")
    cfg = EmissorEmpresa(empresa_id=1)
    assert garantir_municipio(Db(), e, cfg) == "5300108" and cfg.cod_municipio == "5300108"
    sem = Empresa(cnpj="60741606000100", razao_social="Y")
    assert garantir_municipio(Db(), sem, EmissorEmpresa(empresa_id=2)) is None
