"""DANFSe pelo gerador oficial da Receita Federal (calculadora-rtc-gerador-danfse), com o gerador
próprio (danfse.py, mesma NT 008/2026) como reserva.

O gerador da Receita roda num contêiner interno (deploy/danfse), sem acesso de fora; o XML nunca sai
do servidor. Endereço em CONTASK_DANFSE_URL; vazio (instalação local) usa só o gerador próprio.
Qualquer falha (fora do ar, tempo esgotado, XML recusado, resposta que não é PDF) cai no gerador
próprio, que também valida o XML. O log nunca leva o XML nem dados da nota.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import config
from app.fiscal.danfse import gerar_danfse

log = logging.getLogger(__name__)

RECEITA = "receita"
PROPRIO = "proprio"
# stc do gerador da Receita: 0 válida, 1 substituída, 2 cancelada
STC = {None: "0", "SUBSTITUÍDA": "1", "CANCELADA": "2"}
TEMPO = httpx.Timeout(15.0, connect=3.0)


def receita_ativa() -> bool:
    return bool(config().danfse_url.strip())


def gerar(xml: bytes, *, marca_dagua: str | None = None) -> tuple[bytes, str]:
    """Devolve (pdf, origem): origem é "receita" ou "proprio"."""
    if receita_ativa():
        pdf = _pela_receita(xml, marca_dagua)
        if pdf is not None:
            return pdf, RECEITA
    return gerar_danfse(xml, marca_dagua=marca_dagua), PROPRIO


def _pela_receita(xml: bytes, marca: str | None) -> bytes | None:
    url = config().danfse_url.strip().rstrip("/") + "/api/danfse"
    try:
        r = httpx.post(url, content=xml, params={"stc": STC.get(marca, "0"), "canhoto": "false"},
                       headers={"Content-Type": "application/xml"}, timeout=TEMPO)
    except httpx.HTTPError as e:
        log.warning("Gerador de DANFSe da Receita indisponível (%s); usando o próprio.", type(e).__name__)
        return None
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        log.warning("Gerador de DANFSe da Receita respondeu %s; usando o próprio.", r.status_code)
        return None
    return r.content
