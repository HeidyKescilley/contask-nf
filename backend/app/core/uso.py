"""Limite mensal de XMLs do plano.

Conta os documentos (NFS-e e eventos) recebidos do ADN em buscas incrementais iniciadas no mês
corrente (horário de Brasília). A carga inicial do histórico ("inicial") e o "refazer" não contam.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import BuscaJob

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
AVISO = 0.8


def inicio_do_mes(agora: datetime | None = None) -> datetime:
    a = (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)
    return a.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def xmls_no_mes(db: Session, agora: datetime | None = None) -> int:
    ini = inicio_do_mes(agora)
    return int(db.scalar(select(func.coalesce(func.sum(BuscaJob.docs_recebidos), 0))
                         .where(BuscaJob.tipo == "incremental", BuscaJob.iniciado_em >= ini)) or 0)


def limite_atingido(db: Session) -> bool:
    limite = config().limite_xmls_mes
    return limite > 0 and xmls_no_mes(db) >= limite


def resumo(db: Session) -> dict:
    limite = config().limite_xmls_mes
    usados = xmls_no_mes(db)
    pct = (usados / limite) if limite > 0 else 0.0
    return {
        "mes": inicio_do_mes().strftime("%Y-%m"),
        "usados": usados,
        "limite": limite or None,
        "percentual": round(pct * 100, 1) if limite > 0 else None,
        "situacao": "sem_limite" if limite <= 0 else ("atingido" if usados >= limite else
                                                       ("aviso" if pct >= AVISO else "ok")),
    }
