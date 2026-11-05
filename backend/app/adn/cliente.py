"""Cliente mTLS da distribuição do ADN (somente leitura: GET /contribuintes/DFe/{NSU}).

Regras validadas com o ADN real:
- NSU é exclusivo: a próxima chamada usa o maior NSU recebido.
- Sempre enviar cnpjConsulta/cpfConsulta (sem ele, 400 sem código de erro).
- 404 + NENHUM_DOCUMENTO_LOCALIZADO (E2220) = fim da fila.
- Certificado vencido derruba o TLS em vez de responder E2213.
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import secrets
import ssl
import tempfile
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import certifi
import httpx
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, Encoding, PrivateFormat, pkcs12

log = logging.getLogger("contask.adn")

URL_PADRAO = "https://adn.nfse.gov.br"
MAX_TENTATIVAS = 6
ERROS_CERTIFICADO = {"E2210", "E2211", "E2212", "E2213", "E2214"}


class ErroADN(Exception):
    def __init__(self, mensagem: str, codigos: list[str] | None = None):
        super().__init__(mensagem)
        self.codigos = codigos or []


class ErroProcuracao(ErroADN):
    """E2245: a empresa não outorgou procuração ao titular do certificado."""


class ErroCertificadoADN(ErroADN):
    """Certificado recusado (E2210–E2214 ou falha de TLS)."""


class ErroTemporario(ErroADN):
    """Rede, 429 ou 5xx depois de esgotar as tentativas: o job pode ser retomado do NSU salvo."""


@dataclass
class DocDFe:
    nsu: int
    chave: str | None
    tipo_documento: str
    tipo_evento: str | None
    gerado_em: datetime | None
    xml: bytes | None
    erro: str | None = None


@dataclass
class RespostaDFe:
    tipo_consulta: str | None
    fim: bool
    documentos: list[DocDFe] = field(default_factory=list)
    alertas: list[dict] = field(default_factory=list)

    @property
    def maior_nsu(self) -> int | None:
        return max((d.nsu for d in self.documentos), default=None)


def decodificar_xml(b64: str) -> bytes:
    bruto = base64.b64decode(b64, validate=True)
    try:
        return gzip.decompress(bruto)
    except OSError:
        return bruto


def ssl_context(pfx: bytes, senha: str) -> ssl.SSLContext:
    """Carrega o .pfx no contexto via PEM temporário CIFRADO, removido logo em seguida."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        chave, cert, extras = pkcs12.load_key_and_certificates(pfx, senha.encode("utf-8"))
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    senha_tmp = secrets.token_bytes(32)
    pem = chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, BestAvailableEncryption(senha_tmp))
    pem += cert.public_bytes(Encoding.PEM)
    for c in extras or []:
        pem += c.public_bytes(Encoding.PEM)
    fd, caminho = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        ctx.load_cert_chain(caminho, password=senha_tmp)
    finally:
        os.remove(caminho)
    return ctx


def _dt(v: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def _erro_tls(e: Exception) -> bool:
    texto = f"{e!r} {getattr(e, '__cause__', '')!r}".upper()
    return any(s in texto for s in ("SSL", "TLS", "CERTIFICATE", "HANDSHAKE", "RECORD_LAYER"))


class ClienteADN:
    def __init__(self, *, pfx: bytes | None = None, senha: str | None = None, base_url: str = URL_PADRAO,
                 transport: httpx.BaseTransport | None = None, dormir: Callable[[float], None] = time.sleep,
                 timeout: float = 60.0):
        kwargs: dict = {"base_url": base_url, "timeout": timeout,
                        "headers": {"Accept": "application/json", "User-Agent": "ContaskNF/0.1"}}
        if transport is not None:
            kwargs["transport"] = transport
        else:
            kwargs["verify"] = ssl_context(pfx, senha)
        self._http = httpx.Client(**kwargs)
        self._dormir = dormir

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._http.close()

    def distribuicao(self, nsu: int, *, cnpj: str | None = None, cpf: str | None = None,
                     ao_esperar: Callable[[str], None] | None = None) -> RespostaDFe:
        if bool(cnpj) == bool(cpf):
            raise ValueError("Informe exatamente um entre cnpj e cpf (E2244).")
        params = {"lote": "true", **({"cnpjConsulta": cnpj} if cnpj else {"cpfConsulta": cpf})}
        r = self._get(f"/contribuintes/DFe/{nsu}", params, ao_esperar)
        return self._interpretar(r)

    # --- HTTP com retentativas ------------------------------------------------------

    def _get(self, url: str, params: dict, ao_esperar) -> httpx.Response:
        espera, ultimo = 2.0, "sem resposta"
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                r = self._http.get(url, params=params)
            except httpx.TransportError as e:
                if _erro_tls(e):
                    raise ErroCertificadoADN(
                        "O ADN recusou a conexão com o certificado (vencido, revogado ou inválido).") from None
                ultimo = f"falha de rede ({type(e).__name__})"
            else:
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    try:
                        espera = max(float(ra), 1.0) if ra else espera
                    except ValueError:
                        pass
                    ultimo = "limite de requisições (429)"
                elif r.status_code >= 500:
                    ultimo = f"erro do servidor ({r.status_code})"
                else:
                    return r
            if tentativa == MAX_TENTATIVAS:
                break
            if ao_esperar:
                ao_esperar(f"{ultimo}; nova tentativa em {espera:.0f}s ({tentativa}/{MAX_TENTATIVAS - 1})")
            self._dormir(espera)
            espera = min(espera * 2, 120.0)
        raise ErroTemporario(f"O ADN não respondeu após {MAX_TENTATIVAS} tentativas: {ultimo}.")

    def _interpretar(self, r: httpx.Response) -> RespostaDFe:
        try:
            d = r.json()
        except ValueError:
            raise ErroADN(f"Resposta inesperada do ADN (HTTP {r.status_code}).") from None
        erros = d.get("Erros") or []
        codigos = [str(e.get("Codigo")) for e in erros if e.get("Codigo")]
        texto = "; ".join(f"{e.get('Codigo')}: {e.get('Descricao')}" for e in erros) or None
        status = d.get("StatusProcessamento")

        if r.status_code == 404 and (status == "NENHUM_DOCUMENTO_LOCALIZADO" or "E2220" in codigos):
            return RespostaDFe(tipo_consulta=d.get("TipoConsulta"), fim=True, alertas=d.get("Alertas") or [])
        if "E2245" in codigos:
            raise ErroProcuracao(texto or "Sem procuração.", codigos)
        if set(codigos) & ERROS_CERTIFICADO:
            raise ErroCertificadoADN(texto, codigos)
        if "E2244" in codigos:
            log.error("E2244 (cnpjConsulta e cpfConsulta juntos): erro de programação. %s", texto)
            raise ErroADN(texto, codigos)
        if r.status_code != 200:
            raise ErroADN(texto or f"O ADN recusou a consulta (HTTP {r.status_code}, {status}).", codigos)

        docs = []
        for item in d.get("LoteDFe") or []:
            doc = DocDFe(nsu=int(item["NSU"]), chave=item.get("ChaveAcesso"), tipo_documento=item.get("TipoDocumento") or "",
                         tipo_evento=item.get("TipoEvento"), gerado_em=_dt(item.get("DataHoraGeracao")), xml=None)
            try:
                doc.xml = decodificar_xml(item.get("ArquivoXml") or "")
                if not doc.xml.lstrip().startswith(b"<"):
                    raise ValueError("conteúdo não é XML")
            except Exception as e:  # noqa: BLE001 - registra e segue; o documento fica com erro
                doc.xml, doc.erro = None, f"ArquivoXml inválido: {e}"
            docs.append(doc)
        return RespostaDFe(tipo_consulta=d.get("TipoConsulta"), fim=not docs, documentos=docs,
                           alertas=d.get("Alertas") or [])
