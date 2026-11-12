"""Exportações: prévia ao vivo, geração em segundo plano, histórico e download."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.escopo import escritorio_atual, obter_empresa, obter_exportacao
from app.core.config import config
from app.core.db import sessao
from app.jobs import exportador_ativo
from app.jobs.exportador import Filtros, gerar, nome_arquivo, previa
from app.models import Empresa, Exportacao

router = APIRouter(prefix="/api", tags=["exportacoes"])


def _empresa(db: Session, empresa_id: int, escritorio_id: int) -> Empresa:
    return obter_empresa(db, empresa_id, escritorio_id)


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
def previa_exportacao(empresa_id: int, dados: dict, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    return previa(db, empresa_id, _filtros(dados))


def _regra_teste(db: Session, esc: int, f: Filtros) -> None:
    """Teste grátis: uma exportação, com período definido de até 30 dias."""
    from app.core.escritorios import em_teste, exportacoes_do_escritorio
    if not em_teste(db, esc):
        return
    cfg = config()
    if exportacoes_do_escritorio(db, esc) >= cfg.teste_max_exportacoes:
        raise HTTPException(402, "O teste grátis permite uma exportação, e ela já foi feita. As exportações ficam "
                                 "liberadas ao assinar o plano: fale com o suporte do Contask NF.")
    if not f.inicio or not f.fim or (f.fim - f.inicio).days + 1 > cfg.teste_max_dias_exportacao:
        raise HTTPException(422, f"No teste grátis, a exportação vale para um período de até "
                                 f"{cfg.teste_max_dias_exportacao} dias. Informe as datas inicial e final.")


@router.post("/empresas/{empresa_id}/exportacoes", status_code=201)
def criar_exportacao(empresa_id: int, dados: dict, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    f = _filtros(dados)
    _regra_teste(db, esc, f)
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
def historico(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    # Da empresa + as de "todas as empresas" feitas neste escritório
    itens = db.scalars(select(Exportacao).join(Empresa, Empresa.id == Exportacao.empresa_id)
                       .where(Empresa.escritorio_id == esc,
                              or_(Exportacao.empresa_id == empresa_id,
                                  func.json_extract(Exportacao.filtros, "$.escopo") == "todas"))
                       .order_by(Exportacao.criado_em.desc(), Exportacao.id.desc()).limit(50)).all()
    return [_out(db, x) for x in itens]


@router.get("/exportacoes/{exp_id}/arquivo")
def baixar(exp_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    x = obter_exportacao(db, exp_id, esc)
    if x.status != "concluido" or not x.zip_path:
        raise HTTPException(409, "A exportação ainda não terminou.")
    p = config().dados_dir / x.zip_path
    if not p.is_file():
        raise HTTPException(410, "O arquivo desta exportação não existe mais. Gere de novo.")
    e = db.get(Empresa, x.empresa_id)
    return FileResponse(p, media_type="application/zip", filename=nome_arquivo(e, Filtros.model_validate(x.filtros)))
