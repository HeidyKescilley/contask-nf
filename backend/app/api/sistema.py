from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import cripto, uso
from app.core.db import sessao
from app.models import Empresa

router = APIRouter(prefix="/api", tags=["sistema"])

VERSAO = "0.1.0"


@router.get("/saude")
def saude(db: Session = Depends(sessao)):
    modo = db.execute(text("PRAGMA journal_mode")).scalar()
    empresas = db.scalar(select(func.count()).select_from(Empresa))
    tem_contabilidade = db.scalar(select(func.count()).select_from(Empresa).where(Empresa.is_contabilidade)) > 0
    return {
        "versao": VERSAO,
        "banco": {"ok": True, "journal_mode": modo},
        "chave_mestra": cripto.chave_disponivel(),
        "empresas": empresas,
        "tem_contabilidade": tem_contabilidade,
    }


@router.get("/ping")
def ping():
    """Público: para o monitor de disponibilidade e o healthcheck do contêiner."""
    return {"ok": True}


@router.get("/uso")
def uso_do_mes(db: Session = Depends(sessao)):
    return uso.resumo(db)
