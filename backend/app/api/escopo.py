"""Empresa, nota, job e exportação só existem se forem do escritório da sessão. Caso contrário, 404."""
from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models import BuscaJob, Empresa, Exportacao, Nota


def escritorio_atual(request: Request) -> int:
    u = getattr(request.state, "usuario", None)
    if u is None:
        raise HTTPException(401, "Entre com seu e-mail e senha.")
    return u.escritorio_id


def obter_empresa(db: Session, empresa_id: int, escritorio_id: int) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None or e.escritorio_id != escritorio_id:
        raise HTTPException(404, "Empresa não encontrada.")
    return e


def obter_nota(db: Session, nota_id: int, escritorio_id: int) -> Nota:
    n = db.get(Nota, nota_id)
    if n is None:
        raise HTTPException(404, "Nota não encontrada.")
    e = db.get(Empresa, n.empresa_id)
    if e is None or e.escritorio_id != escritorio_id:
        raise HTTPException(404, "Nota não encontrada.")
    return n


def obter_job(db: Session, job_id: int, escritorio_id: int) -> BuscaJob:
    j = db.get(BuscaJob, job_id)
    if j is None:
        raise HTTPException(404, "Busca não encontrada.")
    e = db.get(Empresa, j.empresa_id)
    if e is None or e.escritorio_id != escritorio_id:
        raise HTTPException(404, "Busca não encontrada.")
    return j


def obter_exportacao(db: Session, exp_id: int, escritorio_id: int) -> Exportacao:
    x = db.get(Exportacao, exp_id)
    if x is None:
        raise HTTPException(404, "Exportação não encontrada.")
    e = db.get(Empresa, x.empresa_id)
    if e is None or e.escritorio_id != escritorio_id:
        raise HTTPException(404, "Exportação não encontrada.")
    return x
