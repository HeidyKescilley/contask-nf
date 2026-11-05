"""Exportações: prévia ao vivo, geração em segundo plano, histórico e download."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.core.db import sessao
from app.jobs import exportador_ativo
from app.jobs.exportador import Filtros, gerar, nome_arquivo, previa
from app.models import Empresa, Exportacao

router = APIRouter(prefix="/api", tags=["exportacoes"])


def _empresa(db: Session, empresa_id: int) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise HTTPException(404, "Empresa não encontrada.")
    return e


def _filtros(dados: dict) -> Filtros:
    try:
        return Filtros.model_validate(dados)
    except ValidationError as ex:
        msg = ex.errors()[0].get("msg", "Filtros inválidos.").replace("Value error, ", "")
        raise HTTPException(422, msg) from None


def _out(db: Session, x: Exportacao) -> dict:
    e = db.get(Empresa, x.empresa_id)
    f = Filtros.model_validate(x.filtros)
    return {"id": x.id, "empresa_id": x.empresa_id, "status": x.status, "filtros": x.filtros,
            "descricao": f.descricao(), "total_notas": x.total_notas, "erro": x.erro, "criado_em": x.criado_em,
            "escopo": f.escopo, "arquivo": nome_arquivo(e, f), "disponivel": x.status == "concluido" and bool(x.zip_path)}


@router.post("/empresas/{empresa_id}/exportacoes/previa")
def previa_exportacao(empresa_id: int, dados: dict, db: Session = Depends(sessao)):
    _empresa(db, empresa_id)
    return previa(db, empresa_id, _filtros(dados))


@router.post("/empresas/{empresa_id}/exportacoes", status_code=201)
def criar_exportacao(empresa_id: int, dados: dict, db: Session = Depends(sessao)):
    _empresa(db, empresa_id)
    f = _filtros(dados)
    if not previa(db, empresa_id, f)["total"]:
        raise HTTPException(422, "Nenhuma nota com esses filtros: não há o que exportar.")
    x = Exportacao(empresa_id=empresa_id, filtros=f.model_dump(mode="json"), status="fila")
    db.add(x)
    db.commit()
    ex = exportador_ativo()
    if ex is not None:
        ex.enfileirar(x.id)
    else:  # sem o motor em segundo plano (testes): gera agora
        x.status = "gerando"
        gerar(db, x)
        db.commit()
    return _out(db, x)


@router.get("/empresas/{empresa_id}/exportacoes")
def historico(empresa_id: int, db: Session = Depends(sessao)):
    _empresa(db, empresa_id)
    # Da empresa + as de "todas as empresas" (feitas a partir de qualquer empresa)
    itens = db.scalars(select(Exportacao).where(or_(Exportacao.empresa_id == empresa_id,
                                                    func.json_extract(Exportacao.filtros, "$.escopo") == "todas"))
                       .order_by(Exportacao.criado_em.desc(), Exportacao.id.desc()).limit(50)).all()
    return [_out(db, x) for x in itens]


@router.get("/exportacoes/{exp_id}/arquivo")
def baixar(exp_id: int, db: Session = Depends(sessao)):
    x = db.get(Exportacao, exp_id)
    if x is None:
        raise HTTPException(404, "Exportação não encontrada.")
    if x.status != "concluido" or not x.zip_path:
        raise HTTPException(409, "A exportação ainda não terminou.")
    p = config().dados_dir / x.zip_path
    if not p.is_file():
        raise HTTPException(410, "O arquivo desta exportação não existe mais. Gere de novo.")
    e = db.get(Empresa, x.empresa_id)
    return FileResponse(p, media_type="application/zip", filename=nome_arquivo(e, Filtros.model_validate(x.filtros)))
