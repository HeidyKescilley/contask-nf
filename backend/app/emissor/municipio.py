"""Município (código IBGE) do prestador, descoberto sozinho a partir dos dados da empresa.

Ordem: código já salvo -> código que a BrasilAPI devolveu no cadastro -> nome do município e UF da
empresa (lista do IBGE) -> nova consulta do CNPJ na BrasilAPI, quando a empresa não tem município.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core import ibge
from app.models import EmissorEmpresa, Empresa

ESPERA_CNPJ = 600  # não reconsulta o mesmo CNPJ na BrasilAPI antes disso
_consultados: dict[str, float] = {}


def _valido(cod) -> str | None:
    s = str(cod or "").strip()
    return s if len(s) == 7 and s.isdigit() else None


def _consultar_cnpj(e: Empresa) -> dict | None:
    if time.monotonic() - _consultados.get(e.cnpj, -ESPERA_CNPJ) < ESPERA_CNPJ:
        return None
    _consultados[e.cnpj] = time.monotonic()
    from app.core.brasilapi import BrasilApiErro, consultar
    try:
        return consultar(e.cnpj)
    except BrasilApiErro:
        return None


def garantir_municipio(db: Session, e: Empresa, cfg: EmissorEmpresa) -> str | None:
    """Preenche `cfg.cod_municipio` quando dá para descobrir; devolve o código (ou None)."""
    if _valido(cfg.cod_municipio):
        return cfg.cod_municipio
    cod = _valido((e.dados_brasilapi or {}).get("codigo_municipio_ibge")) or ibge.codigo(e.uf, e.municipio)
    if not cod and not (e.uf and e.municipio):
        d = _consultar_cnpj(e)
        if d:
            e.uf = e.uf or d.get("uf")
            e.municipio = e.municipio or d.get("municipio")
            e.dados_brasilapi = e.dados_brasilapi or d.get("bruto")
            cod = _valido((d.get("bruto") or {}).get("codigo_municipio_ibge")) or ibge.codigo(e.uf, e.municipio)
    if cod:
        cfg.cod_municipio = cod
        db.commit()
    return cod
