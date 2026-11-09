"""Emissor: textos legais, regime tributário, lista com filtros, duplicar, rascunhos e notas recorrentes."""
from datetime import date
from decimal import Decimal

from lxml import etree

from app.api.emissor_notas import modelo_do_xml
from app.emissor import textos
from app.emissor.dps import RESTRITA, Retencoes, montar, serializar
from tests.test_emissor_motor import NS, _dados, _emissao, _pronta, sefin  # noqa: F401 (fixture)
from tests.test_empresas import CLIENTE


def _xinfcomp(sefin_sim, i=-1):
    el = etree.fromstring(sefin_sim.recebidas[i])[0].find("n:serv/n:infoCompl/n:xInfComp", NS)
    return el.text if el is not None else None


# ---------------------------------------------------------------------------
# Textos e variáveis
# ---------------------------------------------------------------------------

def test_compor_e_separar_textos_legais():
    t = textos.compor("Contrato 12", simples=True, procon=True)
    assert t.startswith("Contrato 12 I - \"DOCUMENTO EMITIDO") and t.endswith("BRASILIA - DF") and "\n" not in t
    assert textos.separar(t) == ("Contrato 12", True, True)
    assert textos.compor("", simples=False, procon=False) is None
    assert textos.separar(textos.TEXTO_PROCON) == ("", False, True)


def test_variaveis_de_data():
    v = textos.valores(date(2026, 11, 9))
    assert v["mes_atual"] == "11/2026" and v["mes_anterior"] == "10/2026"
    assert v["primeiro_dia_mes_anterior"] == "01/10/2026" and v["ultimo_dia_mes_anterior"] == "31/10/2026"
    assert v["ultimo_dia_mes_atual"] == "30/11/2026"
    assert textos.valores(date(2027, 1, 5))["mes_anterior"] == "12/2026"
    assert textos.aplicar("Honorários Contábeis {mes_anterior}", date(2026, 11, 9)) == "Honorários Contábeis 10/2026"
    assert textos.desconhecidas("x {mes_atual} {ano}") == ["ano"]
    # dia 31 em mês curto vira o último dia; próxima data estritamente futura
    assert textos.proxima_data(31, date(2027, 2, 1)) == date(2027, 2, 28)
    assert textos.proxima_data(10, date(2026, 11, 10), incluir=False) == date(2026, 12, 10)
    assert textos.proxima_data(5, date(2026, 12, 20)) == date(2027, 1, 5)


# ---------------------------------------------------------------------------
# Emissão com regime e textos
# ---------------------------------------------------------------------------

def test_textos_legais_na_nota(cliente, sefin):
    e, s = _pronta(cliente)
    cfg = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]
    assert cfg["regime_tributario"] is None and cfg["simples"] is True  # veio da BrasilAPI (ME/EPP)
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s, info_complementar="Contrato 12")).json()
    assert n["situacao"] == "autorizada"
    info = _xinfcomp(sefin)
    assert textos.TEXTO_SIMPLES in info and textos.TEXTO_PROCON in info and info.startswith("Contrato 12")
    assert (n["info_usuario"], n["texto_simples"], n["texto_procon"]) == ("Contrato 12", True, True)

    cliente.post("/api/emissor/notas", json=_emissao(e, s, texto_procon=False))
    assert _xinfcomp(sefin) == textos.TEXTO_SIMPLES

    # Lucro presumido: sai do Simples e o texto do Simples não vai, mesmo marcado
    base = {k: cfg[k] for k in ("inscricao_municipal", "op_simples", "reg_ap_trib_sn", "reg_esp_trib", "serie", "proximo_numero")}
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={**base, "proximo_numero": 3, "regime_tributario": "presumido"})
    assert r.status_code == 200, r.text
    assert r.json()["config"]["op_simples"] == "1" and r.json()["config"]["simples"] is False
    cliente.post("/api/emissor/notas", json=_emissao(e, s, texto_simples=True))
    assert _xinfcomp(sefin) == textos.TEXTO_PROCON
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={**base, "op_simples": "1", "regime_tributario": "simples"})
    assert r.status_code == 422 and "ME/EPP ou MEI" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Lista da empresa com filtros
# ---------------------------------------------------------------------------

def test_lista_da_empresa_com_filtros(cliente, sefin):
    e, s = _pronta(cliente)
    a = cliente.post("/api/emissor/notas", json=_emissao(e, s, descricao="Honorários outubro")).json()
    b = cliente.post("/api/emissor/notas", json=_emissao(e, s, valor="250.00", tomador={"documento": "52998224725", "nome": "Maria Silva"})).json()
    url = f"/api/emissor/empresas/{e['id']}/notas"
    hoje = date.today()
    r = cliente.get(url, params={"inicio": hoje.replace(day=1).isoformat(), "fim": hoje.isoformat()}).json()
    assert r["ambiente"] == RESTRITA and [n["id"] for n in r["notas"]] == [b["id"], a["id"]]
    assert r["totais"] == {"quantidade": 2, "autorizadas": 2, "valor_autorizado": 1250.0}
    assert all(n["origem"] == "contask" for n in r["notas"])
    assert [n["id"] for n in cliente.get(url, params={"q": "maria"}).json()["notas"]] == [b["id"]]
    assert [n["id"] for n in cliente.get(url, params={"q": "529.982"}).json()["notas"]] == [b["id"]]
    assert [n["id"] for n in cliente.get(url, params={"q": "outubro"}).json()["notas"]] == [a["id"]]
    assert [n["id"] for n in cliente.get(url, params={"numero": "2"}).json()["notas"]] == [b["id"]]  # nº da DPS
    assert cliente.get(url, params={"situacao": "cancelada"}).json()["notas"] == []
    assert cliente.get(url, params={"inicio": "2020-01-01", "fim": "2020-01-31"}).json()["notas"] == []
    assert cliente.get(url, params={"inicio": "2026-02-01", "fim": "2026-01-01"}).status_code == 422


def test_modelo_do_xml_para_duplicar():
    d = _dados(op="1", retencoes=Retencoes(pis=Decimal("6.50"), cofins=Decimal("30.00"), csll=Decimal("10.00"),
                                           irrf=Decimal("15.00")))
    d.info_complementar = textos.compor("Contrato 7", simples=False, procon=True)
    m = modelo_do_xml(serializar(montar(d)))
    assert m["tomador"]["documento"] == CLIENTE and m["tomador"]["cep"] == "70040010"
    assert (m["ctribnac"], m["cnbs"], m["descricao"], m["valor_servico"]) == ("171901", "113022100", "Honorários contábeis", 1000.0)
    # Só a soma vai no XML (vRetCSLL): reparte pelas alíquotas padrão
    assert (m["ret_pis"], m["ret_cofins"], m["ret_csll"], m["ret_irrf"]) == (6.5, 30.0, 10.0, 15.0)
    assert (m["info_usuario"], m["texto_simples"], m["texto_procon"]) == ("Contrato 7", False, True)


# ---------------------------------------------------------------------------
# Rascunhos
# ---------------------------------------------------------------------------

def test_rascunho_salvo_e_emitido(cliente, sefin):
    e, s = _pronta(cliente)
    corpo = {"empresa_id": e["id"], "dados": {"servico_id": s["id"], "valor": "100,00", "descricao": "Rascunho",
                                              "tomador": {"documento": CLIENTE, "nome": "Tomador"}, "lixo": 1}}
    r = cliente.post("/api/emissor/rascunhos", json=corpo)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert "lixo" not in r.json()["dados"] and r.json()["tomador_nome"] == "Tomador"
    corpo["dados"]["descricao"] = "Rascunho editado"
    assert cliente.put(f"/api/emissor/rascunhos/{rid}", json=corpo).json()["descricao"] == "Rascunho editado"
    assert [x["id"] for x in cliente.get(f"/api/emissor/empresas/{e['id']}/rascunhos").json()] == [rid]
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s, rascunho_id=rid)).json()
    assert n["situacao"] == "autorizada"
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/rascunhos").json() == []
    # Erro de validação não apaga o rascunho
    rid = cliente.post("/api/emissor/rascunhos", json=corpo).json()["id"]
    assert cliente.post("/api/emissor/notas", json=_emissao(e, s, iss_retido=True, rascunho_id=rid)).status_code == 422
    assert cliente.get(f"/api/emissor/rascunhos/{rid}").status_code == 200
    assert cliente.delete(f"/api/emissor/rascunhos/{rid}").status_code == 204


# ---------------------------------------------------------------------------
# Notas recorrentes
# ---------------------------------------------------------------------------

def _recorrente(e, s, **extra):
    dados = {k: v for k, v in _emissao(e, s, descricao="Honorários Contábeis {mes_anterior}").items()
             if k not in ("empresa_id", "competencia")}
    return {"empresa_id": e["id"], "nome": "Honorários mensais", "dia": 5, "competencia": "anterior", "dados": dados, **extra}


def test_recorrente_valida_variaveis(cliente, sefin):
    e, s = _pronta(cliente)
    r = cliente.post("/api/emissor/recorrentes", json=_recorrente(e, s, dados={**_recorrente(e, s)["dados"], "descricao": "Mês {ano}"}))
    assert r.status_code == 422 and "{ano}" in r.json()["detail"]
    nomes = [v["nome"] for v in cliente.get("/api/emissor/variaveis").json()]
    assert "mes_anterior" in nomes and "ultimo_dia_mes_atual" in nomes


def test_recorrente_emite_uma_vez_por_mes(cliente, sefin):
    from app.core.db import nova_sessao
    from app.emissor import recorrencia
    from app.models import NotaRecorrente

    e, s = _pronta(cliente)
    r = cliente.post("/api/emissor/recorrentes", json=_recorrente(e, s))
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["proxima_em"] > date.today().isoformat() and rec["previa"]["descricao"].startswith("Honorários Contábeis ")
    rid = rec["id"]

    with nova_sessao() as db:
        db.get(NotaRecorrente, rid).proxima_em = date(2026, 11, 5)
        db.commit()
        # Antes do dia: nada
        assert recorrencia.executar_pendentes(db, date(2026, 11, 4)) == []
        criadas = recorrencia.executar_pendentes(db, date(2026, 11, 5))
        assert len(criadas) == 1
        # Mesmo dia de novo: não duplica
        assert recorrencia.executar_pendentes(db, date(2026, 11, 5)) == []
        x = db.get(NotaRecorrente, rid)
        assert x.proxima_em == date(2026, 12, 5) and x.ultima_nota_id == criadas[0] and x.ultimo_erro is None

    n = cliente.get(f"/api/emissor/notas/{criadas[0]}").json()
    assert n["descricao"] == "Honorários Contábeis 10/2026" and n["competencia"] == "2026-10-31"
    assert n["recorrente_id"] == rid and n["situacao"] == "autorizada"
    lista = cliente.get(f"/api/emissor/empresas/{e['id']}/recorrentes").json()
    assert lista[0]["ultima_nota"]["numero_nfse"] == "42"


def test_recorrente_mes_perdido_e_erro_sem_gastar_numero(cliente, sefin):
    from app.core.db import nova_sessao
    from app.emissor import recorrencia
    from app.models import EmissorEmpresa, Empresa, NotaRecorrente

    e, s = _pronta(cliente)
    rid = cliente.post("/api/emissor/recorrentes", json=_recorrente(e, s, dia=20)).json()["id"]
    with nova_sessao() as db:
        db.get(NotaRecorrente, rid).proxima_em = date(2026, 10, 20)
        db.commit()
        # Sistema desligado em outubro: em novembro, antes do dia 20, só registra o aviso
        assert recorrencia.executar_pendentes(db, date(2026, 11, 3)) == []
        x = db.get(NotaRecorrente, rid)
        assert x.proxima_em == date(2026, 11, 20) and "10/2026 não foi emitida" in x.ultimo_erro
        assert sefin.recebidas == []

        # Erro antes do número (município apagado): mantém a data e tenta de novo depois
        db.get(EmissorEmpresa, e["id"]).cod_municipio = None
        db.get(Empresa, e["id"]).dados_brasilapi = {}
        db.commit()
        assert recorrencia.executar_pendentes(db, date(2026, 11, 20)) == []
        x = db.get(NotaRecorrente, rid)
        assert x.proxima_em == date(2026, 11, 20) and "município" in x.ultimo_erro
        assert db.get(EmissorEmpresa, e["id"]).proximo_numero == 1 and sefin.recebidas == []


def test_editar_e_pausar_recorrente(cliente, sefin):
    e, s = _pronta(cliente)
    rid = cliente.post("/api/emissor/recorrentes", json=_recorrente(e, s)).json()["id"]
    r = cliente.put(f"/api/emissor/recorrentes/{rid}", json=_recorrente(e, s, ativa=False, dia=15))
    assert r.status_code == 200 and r.json()["proxima_em"] is None and r.json()["dia"] == 15
    r = cliente.put(f"/api/emissor/recorrentes/{rid}", json=_recorrente(e, s, ativa=True, dia=15))
    assert r.json()["proxima_em"] is not None
    assert cliente.delete(f"/api/emissor/recorrentes/{rid}").status_code == 204
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/recorrentes").json() == []
