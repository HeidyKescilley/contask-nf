"""Parâmetros municipais do ADN (só leitura): convênio do município e alíquota do código de serviço.

API "ADN Parâmetros Municipais" (https://adn.nfse.gov.br/parametrizacao, TLS com certificado ICP-Brasil).
Formatos que a API aceita (conferidos em produção em 24/11/2026):
- convênio: GET /{cMun}/convenio  -> parametrosConvenio.aderenteEmissorNacional (1 = sim)
- alíquota: GET /{cMun}/{cTribNac com pontos}.{cTribMun ou 000}/{AAAA-MM-DD}/aliquota, ex. 04.01.01.000;
  200 traz {"aliquotas": {"04.01.01.000": [{"Incidencia": "SIM", "Aliq": 3.5, ...}]}}, 404 "não encontradas".
O 404 não prova recusa: códigos sem alíquota publicada já foram autorizados (DF 01.02.01, SP 17.06.01),
outros foram recusados (E0312). Por isso a validação trata como alerta.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx

from app.adn.cliente import ssl_context

URL = "https://adn.nfse.gov.br/parametrizacao"
VALIDADE_CACHE = 6 * 3600

_cache: dict[str, tuple[float, object]] = {}
_trava = threading.Lock()


class ErroParametros(Exception):
    """Falha de rede ou resposta inesperada: a validação segue com alerta."""


@dataclass
class Convenio:
    aderente_emissor_nacional: bool
    aderente_ambiente_nacional: bool


@dataclass
class Aliquota:
    encontrada: bool
    aliquota: Decimal | None = None
    incidencia: str | None = None


def codigo_servico(ctribnac: str, ctribmun: str | None) -> str:
    """040101 + None -> 04.01.01.000; com código municipal de 3 dígitos, ele entra no lugar do 000."""
    mun = ctribmun if ctribmun and ctribmun.isdigit() and len(ctribmun) == 3 else "000"
    return f"{ctribnac[:2]}.{ctribnac[2:4]}.{ctribnac[4:6]}.{mun}"


def _guardado(chave: str):
    with _trava:
        x = _cache.get(chave)
        return x[1] if x and time.monotonic() - x[0] < VALIDADE_CACHE else None


def _guardar(chave: str, valor) -> None:
    with _trava:
        _cache[chave] = (time.monotonic(), valor)


class ClienteParametros:
    def __init__(self, *, pfx: bytes | None = None, senha: str | None = None, transport: httpx.BaseTransport | None = None,
                 base_url: str = URL, timeout: float = 20.0):
        kw: dict = {"base_url": base_url, "timeout": timeout, "headers": {"Accept": "application/json", "User-Agent": "ContaskNF/0.1"}}
        if transport is not None:
            kw["transport"] = transport
        else:
            kw["verify"] = ssl_context(pfx, senha)
        self._http = httpx.Client(**kw)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def _get(self, caminho: str) -> httpx.Response:
        try:
            return self._http.get(caminho)
        except httpx.HTTPError as e:
            raise ErroParametros(f"sem resposta da API de parâmetros municipais ({type(e).__name__})") from None

    def convenio(self, cmun: str) -> Convenio:
        chave = f"conv:{cmun}"
        if (c := _guardado(chave)) is not None:
            return c
        r = self._get(f"/{cmun}/convenio")
        if r.status_code != 200:
            raise ErroParametros(f"a consulta do convênio respondeu {r.status_code}")
        p = (r.json() or {}).get("parametrosConvenio") or {}
        c = Convenio(aderente_emissor_nacional=p.get("aderenteEmissorNacional") == 1,
                     aderente_ambiente_nacional=p.get("aderenteAmbienteNacional") == 1)
        _guardar(chave, c)
        return c

    def aliquota(self, cmun: str, codigo: str, competencia: date) -> Aliquota:
        chave = f"aliq:{cmun}:{codigo}:{competencia.isoformat()}"
        if (a := _guardado(chave)) is not None:
            return a
        r = self._get(f"/{cmun}/{codigo}/{competencia.isoformat()}/aliquota")
        if r.status_code == 404:
            a = Aliquota(encontrada=False)
        elif r.status_code == 200:
            lista = ((r.json() or {}).get("aliquotas") or {}).get(codigo) or []
            atual = lista[-1] if lista else {}
            a = Aliquota(encontrada=bool(lista), incidencia=atual.get("Incidencia"),
                         aliquota=Decimal(str(atual["Aliq"])) if atual.get("Aliq") is not None else None)
        else:
            raise ErroParametros(f"a consulta da alíquota respondeu {r.status_code}")
        _guardar(chave, a)
        return a


# Injetável nos testes
fabrica = lambda pfx, senha: ClienteParametros(pfx=pfx, senha=senha)  # noqa: E731
