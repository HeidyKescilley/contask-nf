"""Código IBGE do município (7 dígitos) a partir do nome e da UF.

A lista de municípios vem da BrasilAPI e, se ela falhar, da API de localidades do próprio IBGE.
Fica em memória por UF; falhas de rede nunca derrubam a tela, só deixam o código em branco.
"""
from __future__ import annotations

import time
import unicodedata

import httpx

FONTES = (
    "https://brasilapi.com.br/api/ibge/municipios/v1/{uf}?providers=dados-abertos-br,gov,wikipedia",
    "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
)
TIMEOUT = 8.0
ESPERA_FALHA = 600  # segundos sem tentar de novo a mesma UF depois de uma falha

_cache: dict[str, dict[str, str]] = {}
_falhas: dict[str, float] = {}


def normalizar(nome: str | None) -> str:
    """'Brasília' -> 'BRASILIA'; 'Santa Bárbara d'Oeste' -> 'SANTA BARBARA D OESTE'."""
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return " ".join("".join(c if c.isalnum() else " " for c in s.upper()).split())


def _baixar(uf: str, cliente: httpx.Client | None = None) -> dict[str, str] | None:
    c = cliente or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "ContaskNF/0.1", "Accept": "application/json"})
    try:
        for url in FONTES:
            try:
                r = c.get(url.format(uf=uf))
                if r.status_code != 200:
                    continue
                itens = r.json()
            except (httpx.HTTPError, ValueError):
                continue
            mapa = {}
            for m in itens if isinstance(itens, list) else []:
                cod = str(m.get("codigo_ibge") or m.get("id") or "")
                if len(cod) == 7 and cod.isdigit() and m.get("nome"):
                    mapa[normalizar(m["nome"])] = cod
            if mapa:
                return mapa
        return None
    finally:
        if cliente is None:
            c.close()


def municipios(uf: str, cliente: httpx.Client | None = None) -> dict[str, str] | None:
    uf = (uf or "").strip().upper()
    if len(uf) != 2:
        return None
    if uf in _cache:
        return _cache[uf]
    if time.monotonic() - _falhas.get(uf, -ESPERA_FALHA) < ESPERA_FALHA:
        return None
    mapa = _baixar(uf, cliente)
    if mapa:
        _cache[uf] = mapa
    else:
        _falhas[uf] = time.monotonic()
    return mapa


def codigo(uf: str | None, municipio: str | None, cliente: httpx.Client | None = None) -> str | None:
    """Código IBGE de 7 dígitos, ou None se não achar (sem lançar erro)."""
    m = (municipio or "").strip()
    if len(m) == 7 and m.isdigit():
        return m  # já é o código
    if not uf or not m:
        return None
    mapa = municipios(uf, cliente)
    return (mapa or {}).get(normalizar(m))
