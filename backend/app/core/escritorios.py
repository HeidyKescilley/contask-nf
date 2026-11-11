"""Situação e plano de cada escritório (painel de administração).

- suspenso: ninguém do escritório entra; as buscas automáticas e as notas recorrentes param.
- teste: teste grátis (1 empresa e poucos XMLs); com `teste_ate` vencido, o acesso fica bloqueado.
- ativo: uso normal, com o limite de XMLs do escritório (ou o padrão do sistema).
O administrador do sistema nunca é bloqueado, para não perder o acesso ao painel.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import Escritorio

BRASILIA = timezone(timedelta(hours=-3))
SITUACOES = {"teste", "ativo", "suspenso"}


def hoje() -> date:
    return datetime.now(BRASILIA).date()


def motivo_bloqueio(esc: Escritorio | None) -> str | None:
    if esc is None:
        return None
    if esc.situacao == "suspenso":
        return "O acesso do seu escritório está suspenso. Fale com o suporte do Contask NF."
    if esc.situacao == "teste" and esc.teste_ate is not None and esc.teste_ate < hoje():
        return "O período de teste do seu escritório terminou. Fale com o suporte do Contask NF para continuar."
    return None


def bloqueado(db: Session, escritorio_id: int) -> bool:
    return motivo_bloqueio(db.get(Escritorio, escritorio_id)) is not None


def ids_bloqueados(db: Session) -> set[int]:
    return {e.id for e in db.scalars(select(Escritorio)) if motivo_bloqueio(e)}


def em_teste(db: Session, escritorio_id: int) -> bool:
    """Teste grátis: o modo geral (CONTASK_TESTE, instalação de um escritório só) ou o do escritório."""
    if config().teste:
        return True
    esc = db.get(Escritorio, escritorio_id)
    return esc is not None and esc.situacao == "teste"


def limite_xmls(db: Session, escritorio_id: int) -> int:
    """XMLs novos por mês (0 = sem limite): o do escritório ou o padrão do sistema."""
    esc = db.get(Escritorio, escritorio_id)
    if esc is not None and esc.limite_xmls_mes is not None:
        return esc.limite_xmls_mes
    return config().limite_xmls_mes


def no_dia(ano: int, mes: int, dia: int) -> date:
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def mes_seguinte(d: date, dia: int | None = None) -> date:
    """Mesmo dia (ou o dia de vencimento) no mês seguinte; meses curtos usam o último dia."""
    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return no_dia(ano, mes, dia or d.day)
