"""Limite mensal de XMLs do plano.

Conta os documentos (NFS-e e eventos) recebidos do ADN em buscas incrementais iniciadas no mês
corrente (horário de Brasília). A carga inicial do histórico ("inicial") e o "refazer" não contam.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.core.escritorios import em_teste, emissoes_do_escritorio, exportacoes_do_escritorio, limite_xmls
from app.models import BuscaJob, DocumentoDfe, Empresa

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
AVISO = 0.8


def inicio_do_mes(agora: datetime | None = None) -> datetime:
    a = (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)
    return a.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _do_escritorio(consulta, escritorio_id: int):
    return consulta.join(Empresa, Empresa.id == BuscaJob.empresa_id).where(Empresa.escritorio_id == escritorio_id)


def xmls_no_mes(db: Session, escritorio_id: int, agora: datetime | None = None) -> int:
    ini = inicio_do_mes(agora)
    consulta = select(func.coalesce(func.sum(BuscaJob.docs_recebidos), 0)).where(
        BuscaJob.tipo == "incremental", BuscaJob.iniciado_em >= ini)
    return int(db.scalar(_do_escritorio(consulta, escritorio_id)) or 0)


def limite_atingido(db: Session, escritorio_id: int) -> bool:
    limite = limite_xmls(db, escritorio_id)
    return limite > 0 and xmls_no_mes(db, escritorio_id) >= limite


# --- teste grátis ---------------------------------------------------------------

class LimiteTeste(Exception):
    """Mensagem pensada para ser mostrada ao usuário."""


def xmls_baixados(db: Session, escritorio_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(DocumentoDfe).join(Empresa, Empresa.id == DocumentoDfe.empresa_id)
                         .where(Empresa.escritorio_id == escritorio_id)) or 0)


def exigir_vaga_empresa(db: Session, escritorio_id: int, novas: int = 1) -> None:
    cfg = config()
    if not em_teste(db, escritorio_id):
        return
    atuais = int(db.scalar(select(func.count()).select_from(Empresa).where(
        Empresa.escritorio_id == escritorio_id, Empresa.is_contabilidade.is_(False))) or 0)
    if atuais + novas > cfg.teste_max_empresas:
        from app.core.escritorios import CONTRATE
        raise LimiteTeste(f"No teste grátis dá para cadastrar {cfg.teste_max_empresas} empresa, além do escritório. "
                          f"{CONTRATE}")


def resumo(db: Session, escritorio_id: int) -> dict:
    cfg = config()
    if em_teste(db, escritorio_id):
        return {"mes": inicio_do_mes().strftime("%Y-%m"), "usados": xmls_baixados(db, escritorio_id), "limite": None,
                "percentual": None, "situacao": "teste",
                "teste": {"max_empresas": cfg.teste_max_empresas,
                          "max_emissoes": cfg.teste_max_emissoes, "emissoes": emissoes_do_escritorio(db, escritorio_id),
                          "max_exportacoes": cfg.teste_max_exportacoes,
                          "exportacoes": exportacoes_do_escritorio(db, escritorio_id),
                          "max_dias_exportacao": cfg.teste_max_dias_exportacao}}
    limite = limite_xmls(db, escritorio_id)
    usados = xmls_no_mes(db, escritorio_id)
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
