"""Cliente mTLS da Sefin Nacional: emissão (POST /nfse), consulta por DPS e por chave e eventos.

Em produção só é chamado quando CONTASK_EMISSOR_PRODUCAO=true (regra do projeto). O POST de emissão
NUNCA é repetido às cegas: depois de falha de rede, quem chama consulta /dps/{id} antes de reenviar.
"""
from __future__ import annotations

import base64
import gzip
from dataclasses import dataclass, field

import httpx

from app.adn.cliente import ssl_context

URLS = {
    1: "https://sefin.nfse.gov.br/SefinNacional",
    2: "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional",
}


class ErroSefin(Exception):
    """Falha de comunicação (rede, TLS, 5xx). O resultado da emissão é desconhecido."""


@dataclass
class Resposta:
    ok: bool
    status: int
    chave: str | None = None
    xml: bytes | None = None                              # NFS-e (emissão) ou evento
    erros: list[dict] = field(default_factory=list)       # [{codigo, descricao, complemento}]
    alertas: list[dict] = field(default_factory=list)


def compactar(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def descompactar(b64: str) -> bytes:
    bruto = base64.b64decode(b64)
    try:
        return gzip.decompress(bruto)
    except OSError:
        return bruto


def _erros(d: dict) -> list[dict]:
    brutos = d.get("erros") or d.get("Erros") or d.get("erro") or []
    if isinstance(brutos, dict):
        brutos = [brutos]  # a rota de eventos às vezes devolve "erro" como objeto, às vezes como lista
    saida = []
    for e in brutos:
        if not isinstance(e, dict):
            continue
        e = {k.lower(): v for k, v in e.items()}
        saida.append({"codigo": e.get("codigo"), "descricao": e.get("descricao"), "complemento": e.get("complemento")})
    return saida


class ClienteSefin:
    def __init__(self, *, ambiente: int, pfx: bytes | None = None, senha: str | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 90.0):
        kwargs: dict = {"base_url": URLS[ambiente], "timeout": timeout,
                        "headers": {"Accept": "application/json", "User-Agent": "ContaskNF/1.0"}}
        if transport is not None:
            kwargs["transport"] = transport
        else:
            kwargs["verify"] = ssl_context(pfx, senha)
        self._http = httpx.Client(**kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def _req(self, metodo: str, url: str, **kw) -> httpx.Response:
        try:
            r = self._http.request(metodo, url, **kw)
        except httpx.TransportError as e:
            raise ErroSefin(f"Sem resposta da Sefin ({type(e).__name__}).") from None
        if r.status_code >= 500 or r.status_code == 429:
            raise ErroSefin(f"A Sefin respondeu com erro temporário (HTTP {r.status_code}).")
        return r

    @staticmethod
    def _json(r: httpx.Response) -> dict:
        try:
            return r.json()
        except ValueError:
            raise ErroSefin(f"Resposta inesperada da Sefin (HTTP {r.status_code}).") from None

    def emitir(self, dps_xml: bytes) -> Resposta:
        r = self._req("POST", "/nfse", json={"dpsXmlGZipB64": compactar(dps_xml)})
        d = self._json(r)
        if r.status_code == 201 and d.get("nfseXmlGZipB64"):
            return Resposta(True, 201, chave=d.get("chaveAcesso"), xml=descompactar(d["nfseXmlGZipB64"]),
                            alertas=d.get("alertas") or [])
        return Resposta(False, r.status_code, erros=_erros(d) or [{"codigo": str(r.status_code), "descricao": "Recusada pela Sefin.", "complemento": None}])

    def chave_da_dps(self, id_dps: str) -> str | None:
        """Chave da NFS-e gerada a partir da DPS, ou None se nenhuma nota foi gerada."""
        r = self._req("GET", f"/dps/{id_dps}")
        if r.status_code == 404:
            return None
        d = self._json(r)
        if r.status_code != 200:
            raise ErroSefin("; ".join(f"{e['codigo']}: {e['descricao']}" for e in _erros(d)) or f"HTTP {r.status_code}")
        return d.get("chaveAcesso")

    def obter_nfse(self, chave: str) -> bytes:
        r = self._req("GET", f"/nfse/{chave}")
        d = self._json(r)
        if r.status_code != 200 or not d.get("nfseXmlGZipB64"):
            raise ErroSefin(f"Não foi possível baixar a NFS-e {chave} (HTTP {r.status_code}).")
        return descompactar(d["nfseXmlGZipB64"])

    def registrar_evento(self, chave: str, pedido_xml: bytes) -> Resposta:
        r = self._req("POST", f"/nfse/{chave}/eventos", json={"pedidoRegistroEventoXmlGZipB64": compactar(pedido_xml)})
        d = self._json(r)
        if r.status_code == 201 and d.get("eventoXmlGZipB64"):
            return Resposta(True, 201, chave=chave, xml=descompactar(d["eventoXmlGZipB64"]))
        return Resposta(False, r.status_code, erros=_erros(d) or [{"codigo": str(r.status_code), "descricao": "Recusado pela Sefin.", "complemento": None}])
