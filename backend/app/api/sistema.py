from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.escopo import escritorio_atual
from app.core import cripto, uso
from app.core.db import sessao

router = APIRouter(prefix="/api", tags=["sistema"])

VERSAO = "0.1.0"


@router.get("/saude")
def saude(db: Session = Depends(sessao)):
    modo = db.execute(text("PRAGMA journal_mode")).scalar()
    return {
        "versao": VERSAO,
        "banco": {"ok": True, "journal_mode": modo},
        "chave_mestra": cripto.chave_disponivel(),
    }


@router.get("/ping")
def ping():
    """Público: para o monitor de disponibilidade e o healthcheck do contêiner."""
    return {"ok": True}


@router.get("/uso")
def uso_do_mes(db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    return uso.resumo(db, esc)
