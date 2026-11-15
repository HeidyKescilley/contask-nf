"""ISSNet do DF: assinatura SHA1/C14N, envelope SOAP, leitura das respostas, canal e monitoramento dos RPS."""
import httpx
import pytest
from lxml import etree

from app.core.db import nova_sessao
from app.emissor import assinatura, motor
from app.emissor.dps import RESTRITA
from app.emissor.issnet import mensagens, rps
from app.emissor.issnet.soap import NS_NFSE, ClienteIssnet, ErroIssnet, cabecalho, envelope, ler_resposta
from app.models import EmissorEmpresa, RpsDisponivel
from tests.adn_simulado import evento_xml, nfse_xml
from tests.certs import criar_pfx
from tests.test_emissor_cadastros import OUTRO
from tests.test_emissor_motor import _dados
from tests.test_empresas import CLIENTE, SENHA, _contabilidade

DS = "http://www.w3.org/2000/09/xmldsig#"


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------

def test_assinatura_do_issnet_usa_c14n_inclusiva_e_sha1():
    raiz = motor.montar(_dados())
    chave, cert = assinatura.carregar_chave(criar_pfx("EMPRESA PROPRIA LTDA", cnpj=OUTRO), SENHA)
    assinatura.assinar(raiz, raiz[0], chave, cert, assinatura.ISSNET)
    algs = [e.get("Algorithm") for e in raiz.find(f"{{{DS}}}Signature").iter() if e.get("Algorithm")]
    assert algs.count("http://www.w3.org/TR/2001/REC-xml-c14n-20010315") == 2
    assert "http://www.w3.org/2000/09/xmldsig#rsa-sha1" in algs and "http://www.w3.org/2000/09/xmldsig#sha1" in algs
    assert assinatura.conferir(raiz, assinatura.ISSNET)
    assert not assinatura.conferir(raiz)  # o perfil da Sefin não confere uma assinatura do ISSNet
    raiz[0].find(f"{{{NS_NFSE}}}serv/{{{NS_NFSE}}}cServ/{{{NS_NFSE}}}xDescServ").text = "alterado"
    assert not assinatura.conferir(raiz, assinatura.ISSNET)


# ---------------------------------------------------------------------------
# SOAP
# ---------------------------------------------------------------------------

def _soap(metodo: str, dados: str) -> bytes:
    """Como o ISSNet de produção responde (visto em 15/11/2026): dados direto em {Metodo}Response, com BOM."""
    return ('\ufeff<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<{metodo}Response xmlns="{NS_NFSE}">{dados}</{metodo}Response></s:Body></s:Envelope>').encode("utf-8")


ERRO = (f'<ConsultarDpsDisponivelResposta xmlns="{NS_NFSE}"><ListaMensagemRetorno><MensagemRetorno>'
        f'<Codigo>E160</Codigo><Mensagem>Inscrição municipal inválida</Mensagem><Correcao>Confira a IM</Correcao>'
        f'</MensagemRetorno></ListaMensagemRetorno></ConsultarDpsDisponivelResposta>')


def _dados_do_pedido(req: httpx.Request):
    """(método, XML de dados) de um pedido SOAP do cliente."""
    env = etree.fromstring(req.content)
    metodo = env.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
    # Como o servidor: o XML de dados fica no envelope, e a assinatura é conferida com os namespaces dele
    return etree.QName(metodo).localname, metodo.find("nfseDadosMsg")[0]


def test_envelope_no_formato_aceito_pela_producao():
    corpo = envelope("ConsultarDpsDisponivel",
                     '<?xml version="1.0"?>' + mensagens.consultar_dps_disponivel(OUTRO, "12345", 2), cabecalho())
    texto = corpo.decode()
    # prefixo do serviço declarado no Envelope; dados ANTES do cabeçalho; XML embutido, não escapado
    assert texto.index("<soap:Envelope") < texto.index(f'xmlns:ws="{NS_NFSE}"') < texto.index("<ws:ConsultarDpsDisponivel>")
    assert texto.index("<nfseDadosMsg>") < texto.index("<nfseCabecMsg>") and "&lt;" not in texto
    assert texto.count("<?xml") == 1
    metodo, dados = _dados_do_pedido(httpx.Request("POST", "https://x", content=corpo))
    assert metodo == "ConsultarDpsDisponivel"
    assert [etree.QName(e).localname for e in dados] == ["Prestador", "Pagina"]
    assert dados.find(f"{{{NS_NFSE}}}Prestador/{{{NS_NFSE}}}IM").text == "12345"
    with pytest.raises(ValueError):
        envelope("ApagarTudo", "<x/>", "<c/>")
    with pytest.raises(etree.XMLSyntaxError):
        envelope("GerarNfse", "<x>", "<c/>")


def test_le_resposta_com_erros_sucesso_e_soap_fault():
    r = ler_resposta("ConsultarDpsDisponivel", _soap("ConsultarDpsDisponivel", ERRO))
    assert not r.ok and r.erros == [{"codigo": "E160", "descricao": "Inscrição municipal inválida", "complemento": "Confira a IM"}]
    assert "E160: Inscrição municipal inválida (Confira a IM)" == mensagens.texto_erros(r.erros)
    # S000 do ValidarXml vem na ListaMensagemRetorno, mas é sucesso
    ok = (f'<ValidarXmlResposta xmlns="{NS_NFSE}"><ListaMensagemRetorno><MensagemRetorno><Codigo>S000</Codigo>'
          f'<Mensagem>XML válido.</Mensagem></MensagemRetorno></ListaMensagemRetorno></ValidarXmlResposta>')
    r = ler_resposta("ValidarXml", _soap("ValidarXml", ok))
    assert r.ok and r.alertas[0]["codigo"] == "S000"
    falha = (b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><soap:Fault>'
             b'<faultcode>soap:Client</faultcode><faultstring>Certificado inv\xc3\xa1lido</faultstring></soap:Fault>'
             b'</soap:Body></soap:Envelope>')
    with pytest.raises(ErroIssnet, match="Certificado inválido"):
        ler_resposta("GerarNfse", falha)
    with pytest.raises(ErroIssnet):
        ler_resposta("GerarNfse", b"<html>erro</html")


def test_cliente_manda_soapaction_e_trata_403_e_5xx():
    pedidos = []

    def responder(req: httpx.Request):
        pedidos.append(req)
        return {1: httpx.Response(200, content=_soap("ConsultarDpsDisponivel", ERRO)),
                2: httpx.Response(403, text="Proibido"),
                3: httpx.Response(503, text="fora")}[len(pedidos)]

    with ClienteIssnet(ambiente=RESTRITA, transport=httpx.MockTransport(responder)) as cli:
        assert cli.chamar("ConsultarDpsDisponivel", "<x/>").erros[0]["codigo"] == "E160"
        with pytest.raises(ErroIssnet, match="certificado"):
            cli.chamar("ConsultarDpsDisponivel", "<x/>")
        with pytest.raises(ErroIssnet, match="temporário"):
            cli.chamar("ConsultarDpsDisponivel", "<x/>")
    assert pedidos[0].headers["SOAPAction"] == f'"{NS_NFSE}/ConsultarDpsDisponivel"'
    assert "homologacao" in str(pedidos[0].url)


def test_mensagens_de_consulta_e_leitura_da_nfse():
    d = etree.fromstring(mensagens.consultar_nfse_por_dps(OUTRO, "999", "8", 42).encode())
    ident = d[0]
    assert [etree.QName(e).localname for e in ident] == ["NumDPS", "SerieDPS"]  # ordem do schema_v101
    assert ident[0].text == "42" and ident[1].text == "8"
    resp = (f'<GerarNfseResposta xmlns="{NS_NFSE}"><ListaNfse><CompNfse><NFSe versao="1.01"><infNFSe Id="NFS1">'
            f'<nNFSe>15</nNFSe></infNFSe></NFSe></CompNfse></ListaNfse></GerarNfseResposta>')
    r = ler_resposta("GerarNfse", _soap("GerarNfse", resp))
    assert r.ok
    [xml] = mensagens.nfses(r)
    assert etree.fromstring(xml).find(f"{{{NS_NFSE}}}infNFSe/{{{NS_NFSE}}}nNFSe").text == "15"


# ---------------------------------------------------------------------------
# Canal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("municipio,regime,esperado", [
    ("5300108", "presumido", "issnet_df"), ("5300108", "real", "issnet_df"), ("5300108", "simples", "nacional"),
    ("3550308", "presumido", "nacional"),
])
def test_canal_da_empresa(municipio, regime, esperado):
    assert motor.canal(EmissorEmpresa(cod_municipio=municipio, regime_tributario=regime, op_simples="1")) == esperado
    assert motor.canal(None) == "nacional"


# ---------------------------------------------------------------------------
# RPS
# ---------------------------------------------------------------------------

def _lista(numeros, serie="8"):
    itens = "".join(f"<DpsDisponivel><NumDPS>{n}</NumDPS><SerieDPS>{serie}</SerieDPS></DpsDisponivel>" for n in numeros)
    return (f'<ConsultarDpsDisponivelResposta xmlns="{NS_NFSE}"><ListaDpsDisponivel><Prestador><CNPJ>{OUTRO}</CNPJ>'
            f'<IM>999</IM></Prestador>{itens}<Pagina>1</Pagina></ListaDpsDisponivel></ConsultarDpsDisponivelResposta>')


FIM = (f'<ConsultarDpsDisponivelResposta xmlns="{NS_NFSE}"><ListaMensagemRetorno><MensagemRetorno>'
       f'<Codigo>E319</Codigo><Mensagem>Página não encontrada.</Mensagem></MensagemRetorno></ListaMensagemRetorno>'
       f'</ConsultarDpsDisponivelResposta>')


def _erro(cod, msg, raiz="GerarNfseResposta"):
    return (f'<{raiz} xmlns="{NS_NFSE}"><ListaMensagemRetorno><MensagemRetorno><Codigo>{cod}</Codigo>'
            f'<Mensagem>{msg}</Mensagem></MensagemRetorno></ListaMensagemRetorno></{raiz}>')


def _gerada(raiz, chave, lista=True):
    nf = etree.fromstring(nfse_xml(chave, prest=OUTRO, toma=CLIENTE, valor="1.00", numero=7))
    comp = f"<CompNfse>{etree.tostring(nf, encoding='unicode')}</CompNfse>"
    corpo = f"<ListaNfse>{comp}</ListaNfse>" if lista else comp
    return f'<{raiz} xmlns="{NS_NFSE}">{corpo}</{raiz}>'


class IssnetSimulado:
    """ConsultarDpsDisponivel em páginas de 50 (página além do fim responde E319, como na produção);
    GerarNfse, ConsultarNfseDps e CancelarNfse a partir das DPS recebidas."""

    def __init__(self, numeros, serie="8"):
        self.numeros = list(numeros)
        self.serie = serie
        self.erro = False
        self.paginas = []
        self.modo = "ok"  # ok | rejeita | cai_depois | cai_antes
        self.dps: list = []
        self.notas: dict[tuple[str, str], str] = {}  # (serie, numero) -> chave
        self.cancelamentos = 0

    def __call__(self, req: httpx.Request):
        metodo, dados = _dados_do_pedido(req)
        if metodo == "ConsultarDpsDisponivel":
            pagina = int(dados.find(f"{{{NS_NFSE}}}Pagina").text)
            self.paginas.append(pagina)
            if self.erro:
                return httpx.Response(200, content=_soap(metodo, ERRO))
            parte = self.numeros[(pagina - 1) * 50: pagina * 50]
            return httpx.Response(200, content=_soap(metodo, _lista(parte, self.serie) if parte else FIM))
        if metodo == "GerarNfse":
            dps = dados[0]
            self.dps.append(dps)
            assert assinatura.conferir(dps, motor.PERFIS_ISSNET[0])
            if self.modo == "cai_antes":
                raise httpx.ConnectError("sem rede")
            if self.modo == "rejeita":
                return httpx.Response(200, content=_soap(metodo, _erro("E045", "Código de tributação inválido.")))
            inf = dps[0]
            serie, num = (inf.find(f"{{{NS_NFSE}}}{t}").text for t in ("serie", "nDPS"))
            chave = f"530010812{OUTRO}{len(self.notas) + 1:027d}"
            self.notas[(serie, num)] = chave
            self.numeros = [x for x in self.numeros if x != int(num)]
            if self.modo == "cai_depois":
                raise httpx.ReadTimeout("caiu")
            return httpx.Response(200, content=_soap(metodo, _gerada("GerarNfseResposta", chave)))
        if metodo == "ConsultarNfseDps":
            ident = dados.find(f"{{{NS_NFSE}}}IdentificacaoDps")
            chave = self.notas.get((ident[1].text, ident[0].text))
            if chave is None:
                return httpx.Response(200, content=_soap(metodo, _erro("E092", "NFS-e não encontrada.", "ConsultarNfseDpsResposta")))
            return httpx.Response(200, content=_soap(metodo, _gerada("ConsultarNfseDpsResposta", chave, lista=False)))
        if metodo == "CancelarNfse":
            ped = dados[0]
            assert assinatura.conferir(ped, motor.PERFIS_ISSNET[0])
            self.cancelamentos += 1
            chave = ped[0].find(f"{{{NS_NFSE}}}chNFSe").text
            ev = etree.fromstring(evento_xml(chave, "101101"))
            corpo = (f'<CancelarNfseResposta xmlns="{NS_NFSE}"><ListaEvento>{etree.tostring(ev, encoding="unicode")}'
                     f'</ListaEvento></CancelarNfseResposta>')
            return httpx.Response(200, content=_soap(metodo, corpo))
        return httpx.Response(500, text="método inesperado")


def _empresa_id(cliente) -> int:
    assert _contabilidade(cliente).status_code == 200
    return cliente.get("/api/contabilidade").json()["id"]


def _sinc(db, emp, simulado):
    with ClienteIssnet(ambiente=RESTRITA, transport=httpx.MockTransport(simulado)) as cli:
        return rps.sincronizar(db, emp, OUTRO, "999", RESTRITA, cli)


def test_sincroniza_todas_as_paginas_e_reserva_o_menor_numero(cliente):
    emp = _empresa_id(cliente)
    sim = IssnetSimulado(range(1, 61))  # 60 números: duas páginas
    with nova_sessao() as db:
        s = _sinc(db, emp, sim)
        assert s.erro is None and s.disponiveis == 60 and sim.paginas == [1, 2]
        res = rps.resumo(db, emp, RESTRITA)
        assert res.nivel == "ok" and res.faixas == [{"serie": "8", "de": 1, "ate": 60, "quantidade": 60}]
        r = rps.reservar(db, emp, RESTRITA)
        db.commit()
        assert (r.serie, r.numero, r.situacao) == ("8", 1, "reservado")
        assert rps.reservar(db, emp, RESTRITA).numero == 2  # nunca o mesmo número duas vezes
        db.commit()


def test_numero_que_some_da_lista_vira_usado_fora_e_reservado_fica(cliente):
    emp = _empresa_id(cliente)
    sim = IssnetSimulado(range(1, 21))
    with nova_sessao() as db:
        _sinc(db, emp, sim)
        rps.reservar(db, emp, RESTRITA)  # número 1, com uma nota em andamento
        db.commit()
        sim.numeros = list(range(5, 21))  # 1 a 4 sumiram (1 é nosso; 2 a 4 foram usados no portal)
        _sinc(db, emp, sim)
        situacoes = {r.numero: r.situacao for r in db.query(RpsDisponivel).filter_by(empresa_id=emp)}
        assert situacoes[1] == "reservado"
        assert [situacoes[n] for n in (2, 3, 4)] == ["usado_fora"] * 3
        res = rps.resumo(db, emp, RESTRITA)
        assert res.disponiveis == 16 and res.usados_fora == 3 and res.reservados == 1
        assert res.faixas == [{"serie": "8", "de": 5, "ate": 20, "quantidade": 16}]


def test_erro_do_issnet_nao_apaga_a_numeracao(cliente):
    emp = _empresa_id(cliente)
    sim = IssnetSimulado(range(1, 11))
    with nova_sessao() as db:
        _sinc(db, emp, sim)
        sim.erro = True
        s = _sinc(db, emp, sim)
        assert "E160" in s.erro
        res = rps.resumo(db, emp, RESTRITA)
        assert res.disponiveis == 10 and res.usados_fora == 0  # sincronização incompleta não marca nada
        assert res.nivel == "ok" and res.erro


def test_alerta_de_rps_acabando_e_zerado(cliente):
    emp = _empresa_id(cliente)
    with nova_sessao() as db:
        assert rps.resumo(db, emp, RESTRITA).nivel == "sem_dados"
        sim = IssnetSimulado(range(1, 4))
        _sinc(db, emp, sim)
        assert rps.resumo(db, emp, RESTRITA).nivel == "baixo"  # 3 < mínimo de 10
        for _ in range(3):
            nota_rps = rps.reservar(db, emp, RESTRITA)
            nota_rps.situacao = "usado"
        db.commit()
        assert rps.resumo(db, emp, RESTRITA).nivel == "zerado"
        with pytest.raises(rps.SemRps, match="RPS"):
            rps.reservar(db, emp, RESTRITA)


def test_concluir_e_liberar_o_numero_da_nota(cliente):
    emp = _empresa_id(cliente)
    with nova_sessao() as db:
        _sinc(db, emp, IssnetSimulado([7, 8]))
        a = rps.reservar(db, emp, RESTRITA, nota_id=None)
        a.nota_id = None
        db.commit()
        # sem nota vinculada, concluir/liberar não mexem em nada
        rps.concluir(db, 999, autorizada=True)
        rps.liberar(db, 999)
        assert a.situacao == "reservado"
        assert rps.precisa_sincronizar(db, emp, RESTRITA) is False


# ---------------------------------------------------------------------------
# Emissão pelo motor (API) com o ISSNet simulado
# ---------------------------------------------------------------------------

@pytest.fixture()
def issnet(monkeypatch):
    sim = IssnetSimulado(range(1, 31))
    monkeypatch.setattr(motor, "producao_disponivel", lambda: True)  # o ISSNet só tem produção
    monkeypatch.setattr(motor, "fabrica_issnet",
                        lambda amb, pfx, senha: ClienteIssnet(ambiente=amb, transport=httpx.MockTransport(sim)))
    return sim


def _config(cliente, e, **campos):
    cfg = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]
    base = {k: cfg[k] for k in ("inscricao_municipal", "op_simples", "reg_ap_trib_sn", "reg_esp_trib", "serie",
                                "proximo_numero", "regime_tributario")}
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={**base, **campos})
    assert r.status_code == 200, r.text
    return r.json()


def _df_presumido(cliente, im="0776997600106"):
    from tests.test_emissor_motor import _pronta
    e, _ = _pronta(cliente)
    _config(cliente, e, op_simples="1", reg_ap_trib_sn=None, inscricao_municipal=im, regime_tributario="presumido")
    s = cliente.post(f"/api/emissor/empresas/{e['id']}/servicos",
                     json={"descricao": "Transporte municipal", "ctribnac": "160201", "cnbs": "104011111",
                           "ctribmun": "1602", "cindop": "060101", "cclasstrib": "000001"}).json()
    return e, s


def _nota(e, s, **extra):
    return {"empresa_id": e["id"], "servico_id": s["id"], "competencia": "2026-11-09", "valor": "1.00",
            "tomador": TOMADOR_COM_ENDERECO, **extra}


TOMADOR_COM_ENDERECO = {"documento": CLIENTE, "nome": "Tomador Teste Ltda", "cep": "71989000", "cod_municipio": "5300108",
                        "logradouro": "ADE Aguas Claras", "numero": "S/N", "bairro": "Arniqueira"}


def _no(dps, caminho):
    return dps[0].find("/".join(f"{{{NS_NFSE}}}{p}" for p in caminho.split("/")))


def test_emissao_pelo_issnet_usa_o_menor_rps_e_autoriza(cliente, issnet, monkeypatch):
    chamou_sefin = []
    monkeypatch.setattr(motor, "fabrica_cliente", lambda *a: chamou_sefin.append(a))
    e, s = _df_presumido(cliente)
    item = cliente.get(f"/api/emissor/empresas/{e['id']}").json()
    assert item["canal"] == "issnet_df" and item["pronta"], item["pendencias"]
    r = cliente.post("/api/emissor/notas", json=_nota(e, s))
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["situacao"] == "autorizada" and n["canal"] == "issnet_df" and (n["serie"], n["numero"]) == ("8", 1)
    assert n["chave"] and n["numero_nfse"] == "7"
    [dps] = issnet.dps
    assert _no(dps, "tpAmb").text == "1" and _no(dps, "prest/IM").text == "0776997600106"
    assert _no(dps, "serv/cServ/cTribMun").text == "1602" and _no(dps, "valores/trib/tribMun/pAliq") is None
    assert _no(dps, "IBSCBS/cIndOp").text == "060101" and _no(dps, "IBSCBS/valores/trib/gIBSCBS/CST").text == "000"
    assert _no(dps, "finNFSe") is None  # no ISSNet o finNFSe fica dentro do IBSCBS
    assert dps[0].get("Id") == n["id_dps"] and n["id_dps"].endswith("00008000000000000001")
    # o número 1 virou usado; a próxima nota pega o 2
    res = cliente.get(f"/api/emissor/empresas/{e['id']}/rps").json()
    assert res["disponiveis"] == 29 and res["nivel"] == "ok"
    assert cliente.post("/api/emissor/notas", json=_nota(e, s)).json()["numero"] == 2
    assert chamou_sefin == []


def test_rejeicao_mantem_o_rps_e_reenvio_usa_o_mesmo_numero(cliente, issnet):
    e, s = _df_presumido(cliente)
    issnet.modo = "rejeita"
    n = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    assert n["situacao"] == "rejeitada" and "E045" in n["mensagem"]
    issnet.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n['id']}/reenviar", json=_nota(e, s))
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "autorizada" and r.json()["numero"] == n["numero"]
    with nova_sessao() as db:
        assert db.query(RpsDisponivel).filter_by(nota_id=n["id"]).one().situacao == "usado"


def test_falha_de_rede_consulta_a_dps_antes_de_reenviar(cliente, issnet):
    e, s = _df_presumido(cliente)
    issnet.modo = "cai_depois"  # o ISSNet gerou a nota, mas a resposta não chegou
    n = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    assert n["situacao"] == "autorizada" and len(issnet.dps) == 1
    issnet.modo = "cai_antes"   # não chegou ao ISSNet
    n2 = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    assert n2["situacao"] == "pendente" and "pode reenviar" in n2["mensagem"]
    issnet.modo = "ok"
    r = cliente.post(f"/api/emissor/notas/{n2['id']}/reenviar")
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "autorizada" and r.json()["numero"] == n2["numero"]
    assert len(issnet.notas) == 2  # nenhuma nota em duplicidade


def test_sem_rps_disponivel_nao_envia(cliente, issnet):
    e, s = _df_presumido(cliente)
    issnet.numeros = []
    r = cliente.post("/api/emissor/notas", json=_nota(e, s))
    assert r.status_code == 422 and "RPS" in r.json()["detail"]
    assert issnet.dps == []
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/rps").json()["nivel"] == "zerado"


def test_cancelamento_pelo_issnet(cliente, issnet):
    e, s = _df_presumido(cliente)
    n = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    r = cliente.post(f"/api/emissor/notas/{n['id']}/cancelar",
                     json={"motivo": "1", "justificativa": "Erro no valor do serviço"})
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "cancelada" and issnet.cancelamentos == 1


def test_pendencias_do_canal_e_rotas_de_rps(cliente, issnet):
    e, s = _df_presumido(cliente, im=None)
    item = cliente.get(f"/api/emissor/empresas/{e['id']}").json()
    assert any("inscrição municipal" in p for p in item["pendencias"]) and not item["pronta"]
    r = cliente.post("/api/emissor/notas", json=_nota(e, s))
    assert r.status_code == 422 and issnet.dps == [] and issnet.paginas == []
    assert cliente.post(f"/api/emissor/empresas/{e['id']}/rps/atualizar").status_code == 422
    _config(cliente, e, inscricao_municipal="123")
    r = cliente.post(f"/api/emissor/empresas/{e['id']}/rps/atualizar")
    assert r.status_code == 200 and r.json()["disponiveis"] == 30 and r.json()["faixas"][0]["ate"] == 30
    issnet.erro = True
    r = cliente.post(f"/api/emissor/empresas/{e['id']}/rps/atualizar")
    assert r.status_code == 502 and "E160" in r.json()["detail"]
    # do Simples no DF: canal nacional, sem RPS
    _config(cliente, e, regime_tributario="simples", op_simples="3", reg_ap_trib_sn="1")
    assert cliente.get(f"/api/emissor/empresas/{e['id']}/rps").status_code == 409
    # tabela de cTribMun do DF
    cods = cliente.get("/api/emissor/codigos/ctribmun-df", params={"ctribnac": "160201"}).json()
    assert cods[0]["codigo"] == "1602" and "160201" in cods[0]["ctribnac"]


def _dados_issnet(**campos):
    d = _dados()
    d.prestador.inscricao_municipal, d.ctribmun, d.cindop, d.cclasstrib = "999", "1719", "030101", "000001"
    for k, v in campos.items():
        setattr(d, k, v)
    return d


def test_dps_do_issnet_exige_im_ctribmun_e_ibscbs():
    from app.emissor.dps import DpsInvalida, montar_issnet
    montar_issnet(_dados_issnet())
    for campo, valor, msg in (("ctribmun", None, "cTribMun"), ("ctribmun", "12345678901", "cTribMun"),
                              ("cindop", None, "IBSCBS")):
        with pytest.raises(DpsInvalida, match=msg):
            montar_issnet(_dados_issnet(**{campo: valor}))
    d = _dados_issnet()
    d.prestador.inscricao_municipal = None
    with pytest.raises(DpsInvalida, match="inscrição municipal"):
        montar_issnet(d)


def test_regras_vistas_na_producao(cliente, issnet):
    """E0235 (tomador CNPJ sem endereço) barrado antes de gastar RPS; E0713 (pTotTrib, nunca indTotTrib);
    E0008 (dhEmi um pouco no passado)."""
    from datetime import datetime, timedelta
    from app.emissor.dps import BRASILIA
    e, s = _df_presumido(cliente)
    r = cliente.post("/api/emissor/notas", json=_nota(e, s, tomador={"documento": CLIENTE, "nome": "Sem Endereço Ltda"}))
    assert r.status_code == 422 and "E0235" in r.json()["detail"] and issnet.dps == [] and issnet.paginas == []
    n = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    assert n["situacao"] == "autorizada"
    [dps] = issnet.dps
    assert _no(dps, "valores/trib/totTrib/indTotTrib") is None
    assert _no(dps, "valores/trib/totTrib/pTotTrib/pTotTribMun").text == "0.00"
    dh = datetime.fromisoformat(_no(dps, "dhEmi").text)
    assert datetime.now(BRASILIA) - dh >= timedelta(minutes=1)


def test_e0714_reenvia_uma_vez_com_o_outro_perfil(cliente, issnet, monkeypatch):
    e, s = _df_presumido(cliente)
    recusados = []
    original = IssnetSimulado.__call__

    def recusa_o_primeiro_perfil(self, req):
        metodo, dados = _dados_do_pedido(req)
        if metodo == "GerarNfse" and assinatura.conferir(dados[0], motor.PERFIS_ISSNET[0]):
            recusados.append(1)
            return httpx.Response(200, content=_soap(metodo, _erro("E0714", "Arquivo enviado com erro na assinatura.")))
        if metodo == "GerarNfse":
            assert assinatura.conferir(dados[0], motor.PERFIS_ISSNET[1])
            monkeypatch.setattr(assinatura, "conferir", lambda *a, **k: True)  # o simulado confere o 1º perfil
        return original(self, req)

    monkeypatch.setattr(IssnetSimulado, "__call__", recusa_o_primeiro_perfil)
    n = cliente.post("/api/emissor/notas", json=_nota(e, s)).json()
    assert recusados == [1] and n["situacao"] == "autorizada" and len(issnet.notas) == 1


def test_issnet_e_sempre_producao(cliente, issnet, monkeypatch):
    e, _ = _df_presumido(cliente)
    cliente.put(f"/api/emissor/empresas/{e['id']}/producao", json={"liberada": True})
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["ambiente"] == 1
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/producao", json={"liberada": False})
    assert r.status_code == 409 and "homologação" in r.json()["detail"]
    monkeypatch.setattr(motor, "producao_disponivel", lambda: False)
    item = cliente.get(f"/api/emissor/empresas/{e['id']}").json()
    assert any("não tem homologação" in p for p in item["pendencias"]) and not item["pronta"]
