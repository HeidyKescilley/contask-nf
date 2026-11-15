"""ISSNet do DF: assinatura SHA1/C14N, envelope SOAP, leitura das respostas, canal e monitoramento dos RPS."""
from xml.sax.saxutils import escape

import httpx
import pytest
from lxml import etree

from app.core.db import nova_sessao
from app.emissor import assinatura, motor
from app.emissor.dps import RESTRITA
from app.emissor.issnet import mensagens, rps
from app.emissor.issnet.soap import NS_NFSE, ClienteIssnet, ErroIssnet, envelope, ler_resposta
from app.models import EmissorEmpresa, RpsDisponivel
from tests.certs import criar_pfx
from tests.test_emissor_cadastros import OUTRO
from tests.test_emissor_motor import _dados
from tests.test_empresas import SENHA, _contabilidade

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

def _soap(metodo: str, dados: str, embrulhar=True) -> bytes:
    corpo = f"<{metodo}Result>{escape(dados)}</{metodo}Result>" if embrulhar else dados
    return (f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{metodo}Response xmlns="http://nfse.abrasf.org.br">{corpo}</{metodo}Response>'
            f'</soap:Body></soap:Envelope>').encode()


ERRO = (f'<ConsultarDpsDisponivelResposta xmlns="{NS_NFSE}"><ListaMensagemRetorno><MensagemRetorno>'
        f'<Codigo>E160</Codigo><Mensagem>Inscrição municipal inválida</Mensagem><Correcao>Confira a IM</Correcao>'
        f'</MensagemRetorno></ListaMensagemRetorno></ConsultarDpsDisponivelResposta>')


def test_envelope_leva_cabecalho_e_dados_como_texto():
    corpo = envelope("ConsultarDpsDisponivel", mensagens.consultar_dps_disponivel(OUTRO, "12345", 2), "<cabecalho/>")
    env = etree.fromstring(corpo)
    metodo = env[0][0]
    assert etree.QName(metodo).localname == "ConsultarDpsDisponivel"
    dados = etree.fromstring(metodo[1].text.encode())
    assert [etree.QName(e).localname for e in dados] == ["Prestador", "Pagina"]
    assert dados.find(f"{{{NS_NFSE}}}Prestador/{{{NS_NFSE}}}IM").text == "12345"
    with pytest.raises(ValueError):
        envelope("ApagarTudo", "<x/>", "<c/>")


def test_le_resposta_com_erros_e_soap_fault():
    r = ler_resposta("ConsultarDpsDisponivel", _soap("ConsultarDpsDisponivel", ERRO))
    assert not r.ok and r.erros == [{"codigo": "E160", "descricao": "Inscrição municipal inválida", "complemento": "Confira a IM"}]
    assert "E160: Inscrição municipal inválida (Confira a IM)" == mensagens.texto_erros(r.erros)
    # XML de dados direto no Body, sem o invólucro Result
    r = ler_resposta("ConsultarDpsDisponivel", _soap("ConsultarDpsDisponivel", ERRO, embrulhar=False))
    assert r.erros[0]["codigo"] == "E160"
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
    assert pedidos[0].headers["SOAPAction"].endswith('/ConsultarDpsDisponivel"')
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


class IssnetSimulado:
    """Responde ConsultarDpsDisponivel em páginas de 50 a partir da lista atual de números."""

    def __init__(self, numeros):
        self.numeros = list(numeros)
        self.erro = False
        self.paginas = []

    def __call__(self, req: httpx.Request):
        env = etree.fromstring(req.content)
        dados = etree.fromstring(env[0][0][1].text.encode())
        pagina = int(dados.find(f"{{{NS_NFSE}}}Pagina").text)
        self.paginas.append(pagina)
        if self.erro:
            return httpx.Response(200, content=_soap("ConsultarDpsDisponivel", ERRO))
        parte = self.numeros[(pagina - 1) * 50: pagina * 50]
        return httpx.Response(200, content=_soap("ConsultarDpsDisponivel", _lista(parte)))


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
