"""Limite mensal de XMLs do plano.

Conta os documentos (NFS-e e eventos) recebidos do ADN em buscas incrementais iniciadas no mês
corrente (horário de Brasília). A carga inicial do histórico ("inicial") e o "refazer" não contam.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import BuscaJob, DocumentoDfe, Empresa

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


# --- teste grátis ---------------------------------------------------------------

class LimiteTeste(Exception):
    """Mensagem pensada para ser mostrada ao usuário."""


def xmls_baixados(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(DocumentoDfe)) or 0)


def restante_teste(db: Session) -> int | None:
    """XMLs que ainda podem ser baixados no teste; None fora do teste."""
    cfg = config()
    if not cfg.teste:
        return None
    return max(cfg.teste_max_xmls - xmls_baixados(db), 0)


def exigir_vaga_empresa(db: Session, novas: int = 1) -> None:
    cfg = config()
    if not cfg.teste:
        return
    atuais = int(db.scalar(select(func.count()).select_from(Empresa).where(Empresa.is_contabilidade.is_(False))) or 0)
    if atuais + novas > cfg.teste_max_empresas:
        raise LimiteTeste(f"No teste grátis dá para cadastrar {cfg.teste_max_empresas} empresa. "
                          "Assine o plano para liberar todas as empresas.")


def resumo(db: Session) -> dict:
    cfg = config()
    if cfg.teste:
        usados = xmls_baixados(db)
        return {"mes": inicio_do_mes().strftime("%Y-%m"), "usados": usados, "limite": cfg.teste_max_xmls,
                "percentual": round(min(usados / cfg.teste_max_xmls, 1) * 100, 1) if cfg.teste_max_xmls else 100.0,
                "situacao": "teste", "teste": {"max_xmls": cfg.teste_max_xmls, "max_empresas": cfg.teste_max_empresas,
                                               "concluido": usados >= cfg.teste_max_xmls}}
    limite = cfg.limite_xmls_mes
    usados = xmls_no_mes(db)
    pct = (usados / limite) if limite > 0 else 0.0
    return {
        "mes": inicio_do_mes().strftime("%Y-%m"),
        "usados": usados,
        "limite": limite or None,
        "percentual": round(pct * 100, 1) if limite > 0 else None,
        "situacao": "sem_limite" if limite <= 0 else ("atingido" if usados >= limite else
                                                       ("aviso" if pct >= AVISO else "ok")),
        "teste": None,
    }
