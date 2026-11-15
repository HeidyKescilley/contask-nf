"""Cliente SOAP (mTLS) do webservice do ISSNet do DF.

- SOAP 1.1, document/literal wrapped (manual 7.3.1). O XML de dados e o cabeçalho vão embutidos no corpo
  (ver envelope); a resposta vem direto em <{Metodo}Response>.
- Em produção só é chamado com CONTASK_EMISSOR_PRODUCAO=true e a empresa liberada (mesma regra da Sefin).
- GerarNfse NUNCA é repetido às cegas: depois de falha de rede, quem chama consulta ConsultarNfseDps.

Conferido no WSDL de produção (15/11/2026, só abre com certificado): o namespace do serviço é o da NFS-e
nacional, os parâmetros são nfseCabecMsg/nfseDadosMsg (sem namespace) e a resposta vem em
<{Metodo}Response><outputXML>. A consulta por DPS chama ConsultarNfseDps e a por faixa ConsultarNfsePorFaixa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from lxml import etree

from app.adn.cliente import ssl_context

URLS = {
    1: "https://nfse.fazenda.df.gov.br/wsnfsenacional/nfse.asmx",
    2: "https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx",
}
NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SERVICO = NS_NFSE
PARAM_CABECALHO, PARAM_DADOS = "nfseCabecMsg", "nfseDadosMsg"

METODOS = {
    "GerarNfse", "RecepcionarLoteDps", "RecepcionarLoteDpsSincrono", "CancelarNfse", "ConsultarLoteDps",
    "ConsultarNfseDps", "ConsultarNfseServicoPrestado", "ConsultarNfseServicoTomado", "ConsultarNfsePorFaixa",
    "ConsultarDadosCadastrais", "ConsultarDpsDisponivel", "ConsultarUrlNfse", "ValidarXml",
}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


class ErroIssnet(Exception):
    """Falha de comunicação (rede, TLS, 5xx, SOAP Fault). O resultado de uma emissão é desconhecido."""


@dataclass
class Retorno:
    """Resposta lida: o XML de dados e as mensagens de erro e de alerta."""
    xml: etree._Element
    erros: list[dict] = field(default_factory=list)     # [{codigo, descricao, complemento}]
    alertas: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros


def cabecalho(ibscbs: bool = True) -> str:
    """Versão 1.01 quando a DPS leva o grupo IBSCBS; 1.00 sem ele (manual, seção 14)."""
    v = "1.01" if ibscbs else "1.00"
    return f'<cabecalho versao="{v}" xmlns="{NS_NFSE}"><versaoDados>{v}</versaoDados></cabecalho>'


def _sem_declaracao(xml: str) -> str:
    xml = xml.strip()
    if xml.startswith("<?xml"):
        xml = xml[xml.index("?>") + 2:].lstrip()
    return xml


def envelope(metodo: str, dados: str, cab: str) -> bytes:
    """Testado na produção em 15/11/2026: o ISSNet só aceita o XML de dados e o cabeçalho EMBUTIDOS como XML
    (escapados como texto dão E183), com nfseDadosMsg ANTES de nfseCabecMsg e com o prefixo ws declarado no
    Envelope (declarado no elemento do método dá E160)."""
    if metodo not in METODOS:
        raise ValueError(f"Método desconhecido do ISSNet: {metodo}")
    dados, cab = _sem_declaracao(dados), _sem_declaracao(cab)
    for parte in (dados, cab):
        etree.fromstring(parte.encode("utf-8"), parser=_PARSER)  # XML malformado não sai daqui
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{NS_SOAP}" xmlns:ws="{NS_SERVICO}"><soap:Body>'
        f'<ws:{metodo}>'
        f'<{PARAM_DADOS}>{dados}</{PARAM_DADOS}>'
        f'<{PARAM_CABECALHO}>{cab}</{PARAM_CABECALHO}>'
        f'</ws:{metodo}></soap:Body></soap:Envelope>'
    ).encode("utf-8")


def dados_do_envelope(env) -> etree._Element:
    """Raiz do XML de dados (ex.: GerarNfseEnvio) dentro de nfseDadosMsg."""
    corpo = next(e for e in env.iter() if local(e) == "Body")
    return filhos(next(e for e in corpo[0] if local(e) == PARAM_DADOS))[0]


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def filhos(el) -> list:
    return [c for c in el if isinstance(c.tag, str)]


def mensagens(raiz, grupo: str) -> list[dict]:
    saida = []
    for g in raiz.iter():
        if local(g) != grupo:
            continue
        for m in filhos(g):
            campos = {local(c): (c.text or "").strip() for c in filhos(m)}
            saida.append({"codigo": campos.get("Codigo"), "descricao": campos.get("Mensagem"),
                          "complemento": campos.get("Correcao") or None})
    return saida


def _dados_do_envelope(metodo: str, env) -> etree._Element:
    res = next((e for e in env.iter() if local(e) in ("outputXML", f"{metodo}Result")), None)
    if res is not None:
        if filhos(res):
            return filhos(res)[0]
        texto = (res.text or "").strip()
        if not texto:
            raise ErroIssnet("Resposta do ISSNet sem conteúdo.")
        try:
            return etree.fromstring(texto.encode("utf-8"), parser=_PARSER)
        except etree.XMLSyntaxError:
            raise ErroIssnet("Resposta do ISSNet com XML inválido.") from None
    # Sem o invólucro Result: o XML de dados vem direto no Body (ou dentro de {Metodo}Response)
    corpo = next((e for e in env.iter() if local(e) == "Body"), None)
    conteudo = filhos(corpo) if corpo is not None else []
    if conteudo and local(conteudo[0]) == f"{metodo}Response":
        conteudo = filhos(conteudo[0])
    if not conteudo:
        raise ErroIssnet("Resposta do ISSNet sem conteúdo.")
    return conteudo[0]


def ler_resposta(metodo: str, corpo: bytes) -> Retorno:
    """Tira o XML de dados de dentro do envelope SOAP. SOAP Fault vira ErroIssnet."""
    try:
        env = etree.fromstring(corpo, parser=_PARSER)
    except etree.XMLSyntaxError:
        raise ErroIssnet("Resposta inesperada do ISSNet (não é XML).") from None
    falha = next((e for e in env.iter() if local(e) == "Fault"), None)
    if falha is not None:
        texto = next((e.text for e in falha.iter() if local(e) in ("faultstring", "Text") and e.text), "SOAP Fault")
        raise ErroIssnet(f"O ISSNet recusou a chamada: {texto.strip()}")
    dados = _dados_do_envelope(metodo, env)
    lista = mensagens(dados, "ListaMensagemRetorno") + mensagens(dados, "ListaMensagemRetornoLote")
    # Códigos S (ex.: S000 "XML válido" do ValidarXml) vêm na mesma lista, mas não são erro
    sucesso = [m for m in lista if (m.get("codigo") or "").startswith("S")]
    return Retorno(xml=dados, erros=[m for m in lista if m not in sucesso],
                   alertas=mensagens(dados, "ListaMensagemAlertaRetorno") + sucesso)


class ClienteIssnet:
    def __init__(self, *, ambiente: int, pfx: bytes | None = None, senha: str | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 90.0):
        self.ambiente = ambiente
        kwargs: dict = {"timeout": timeout, "headers": {"User-Agent": "ContaskNF/1.0"}}
        if transport is not None:
            kwargs["transport"] = transport
        else:
            kwargs["verify"] = ssl_context(pfx, senha)
        self._http = httpx.Client(**kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def wsdl(self) -> bytes:
        """WSDL do serviço (só leitura), para conferir namespace e parâmetros."""
        try:
            r = self._http.get(URLS[self.ambiente] + "?wsdl")
        except httpx.TransportError as e:
            raise ErroIssnet(f"Sem resposta do ISSNet ({type(e).__name__}).") from None
        if r.status_code != 200:
            raise ErroIssnet(f"O ISSNet não entregou o WSDL (HTTP {r.status_code}).")
        return r.content

    def chamar(self, metodo: str, dados: str, *, ibscbs: bool = True, assinar=None) -> Retorno:
        """`assinar(elemento_de_dados)`, quando dado, assina o XML de dados JÁ DENTRO do envelope e o envelope
        sai como ficou (a C14N inclusiva leva em conta os namespaces do envelope)."""
        env = etree.fromstring(envelope(metodo, dados, cabecalho(ibscbs)), parser=_PARSER)
        if assinar is not None:
            assinar(dados_do_envelope(env))
        # Acentos saem como referência numérica (&#231;): o texto é o mesmo, mas os bytes não dependem de como
        # o servidor decodifica o corpo (acento alterado no caminho invalida a assinatura: E0714)
        corpo = b'<?xml version="1.0" encoding="utf-8"?>' + etree.tostring(env, encoding="ascii", xml_declaration=False)
        self.ultimo_envio = corpo
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS_SERVICO}/{metodo}"'}
        try:
            r = self._http.post(URLS[self.ambiente], content=corpo, headers=headers)
        except httpx.TransportError as e:
            raise ErroIssnet(f"Sem resposta do ISSNet ({type(e).__name__}).") from None
        if r.status_code in (401, 403):
            raise ErroIssnet("O ISSNet recusou o certificado (HTTP 403). Confira se a empresa tem acesso ao "
                             "webservice e se o certificado é ICP-Brasil do tipo A.")
        if r.status_code == 429 or (r.status_code >= 500 and b"Fault" not in r.content):
            raise ErroIssnet(f"O ISSNet respondeu com erro temporário (HTTP {r.status_code}).")
        return ler_resposta(metodo, r.content)
