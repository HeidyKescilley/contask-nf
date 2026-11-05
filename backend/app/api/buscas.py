"""Central de Buscas: estado, ações e eventos em tempo real (SSE)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import sessao
from app.jobs import acordar_fila, gerenciador
from app.jobs.barramento import barramento
from app.jobs.fila import JobEmAndamento, enfileirar
from app.jobs.sincronizador import certificado_da_empresa
from app.models import BuscaJob, BuscaLog, Empresa, SyncEstado

router = APIRouter(prefix="/api", tags=["buscas"])


class NovaBusca(BaseModel):
    tipo: str = "incremental"  # incremental|refazer


def _job_out(db: Session, j: BuscaJob) -> dict:
    e = db.get(Empresa, j.empresa_id)
    s = db.get(SyncEstado, j.empresa_id)
    cert = certificado_da_empresa(db, e) if e else None
    duracao = None
    if j.iniciado_em:
        fim = j.finalizado_em or datetime.now(timezone.utc)
        ini = j.iniciado_em if j.iniciado_em.tzinfo else j.iniciado_em.replace(tzinfo=timezone.utc)
        fim = fim if fim.tzinfo else fim.replace(tzinfo=timezone.utc)
        duracao = max((fim - ini).total_seconds(), 0)
    return {
        "id": j.id, "tipo": j.tipo, "status": j.status, "empresa_id": j.empresa_id,
        "empresa": {"razao_social": e.razao_social, "apelido": e.apelido, "nome_fantasia": e.nome_fantasia, "cnpj": e.cnpj} if e else None,
        "situacao_empresa": s.situacao if s else None, "tipo_consulta": s.tipo_consulta if s else None,
        "certificado": {"titular_nome": cert.titular_nome, "id": cert.id} if cert else None,
        "modo_certificado": e.modo_certificado if e else None,
        "iniciado_em": j.iniciado_em, "finalizado_em": j.finalizado_em, "criado_em": j.criado_em,
        "duracao_s": duracao, "paginas": j.paginas, "docs_recebidos": j.docs_recebidos, "notas_ok": j.notas_ok,
        "eventos_ok": j.eventos_ok, "docs_com_erro": j.docs_com_erro, "eventos_sem_nota": j.eventos_sem_nota,
        "ultimo_nsu": j.ultimo_nsu, "mensagem": j.mensagem,
        "docs_por_min": round(j.docs_recebidos / (duracao / 60), 1) if duracao and duracao > 5 and j.docs_recebidos else None,
    }


@router.get("/buscas")
def estado_buscas(db: Session = Depends(sessao)):
    pend = list(db.scalars(select(BuscaJob).where(BuscaJob.status.in_(["fila", "rodando", "pausado"]))
                           .order_by(BuscaJob.criado_em)))
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    recentes = list(db.scalars(select(BuscaJob).where(BuscaJob.status.in_(["concluido", "erro", "cancelado"]),
                                                      BuscaJob.finalizado_em >= limite)
                               .order_by(BuscaJob.finalizado_em.desc()).limit(30)))
    g = gerenciador()
    return {
        "ativas": [_job_out(db, j) for j in pend],
        "recentes": [_job_out(db, j) for j in recentes],
        "rodando": len([j for j in pend if j.status == "rodando"]),
        "na_fila": len([j for j in pend if j.status == "fila"]),
        "fila_ativa": g is not None,
    }


@router.post("/empresas/{empresa_id}/buscas", status_code=201)
def nova_busca(empresa_id: int, dados: NovaBusca, db: Session = Depends(sessao)):
    if dados.tipo not in ("incremental", "refazer"):
        raise HTTPException(422, "Tipo de busca inválido.")
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise HTTPException(404, "Empresa não encontrada.")
    if not e.ativa:
        raise HTTPException(409, "Empresa inativa. Reative-a para buscar notas.")
    try:
        job = enfileirar(db, empresa_id, dados.tipo)
    except JobEmAndamento as ex:
        raise HTTPException(409, str(ex)) from None
    db.commit()
    acordar_fila()
    barramento.publicar({"tipo": "job", "id": job.id, "empresa_id": empresa_id, "status": job.status})
    return _job_out(db, job)


def _job(db: Session, job_id: int) -> BuscaJob:
    j = db.get(BuscaJob, job_id)
    if j is None:
        raise HTTPException(404, "Busca não encontrada.")
    return j


@router.post("/buscas/{job_id}/pausar")
def pausar(job_id: int, db: Session = Depends(sessao)):
    j = _job(db, job_id)
    if j.status not in ("fila", "rodando"):
        raise HTTPException(409, "Só é possível pausar uma busca na fila ou em andamento.")
    estava = j.status
    j.status = "pausado"
    if estava == "fila":
        db.add(BuscaLog(job_id=j.id, momento=datetime.now(timezone.utc), nivel="info", mensagem="Busca pausada."))
    db.commit()
    barramento.publicar({"tipo": "job", "id": j.id, "empresa_id": j.empresa_id, "status": j.status})
    return _job_out(db, j)


@router.post("/buscas/{job_id}/retomar")
def retomar(job_id: int, db: Session = Depends(sessao)):
    j = _job(db, job_id)
    if j.status not in ("pausado", "erro"):
        raise HTTPException(409, "Só é possível retomar uma busca pausada ou com erro.")
    if j.status == "erro":
        # Erro: abre um novo job que continua do NSU salvo (o histórico do anterior é mantido)
        novo = enfileirar(db, j.empresa_id, "incremental")
        s = db.get(SyncEstado, j.empresa_id)
        if s and s.situacao in ("erro", "sem_procuracao", "erro_certificado", "limite_mes"):
            s.situacao = "buscando"
        db.commit()
        acordar_fila()
        return _job_out(db, novo)
    j.status = "fila"
    db.add(BuscaLog(job_id=j.id, momento=datetime.now(timezone.utc), nivel="info", mensagem="Busca retomada."))
    db.commit()
    acordar_fila()
    barramento.publicar({"tipo": "job", "id": j.id, "empresa_id": j.empresa_id, "status": j.status})
    return _job_out(db, j)


@router.post("/buscas/{job_id}/cancelar")
def cancelar(job_id: int, db: Session = Depends(sessao)):
    j = _job(db, job_id)
    if j.status not in ("fila", "pausado", "rodando"):
        raise HTTPException(409, "Esta busca já terminou.")
    j.status, j.finalizado_em = "cancelado", datetime.now(timezone.utc)
    db.commit()
    barramento.publicar({"tipo": "job", "id": j.id, "empresa_id": j.empresa_id, "status": j.status})
    return _job_out(db, j)


@router.get("/buscas/{job_id}/log")
def log_busca(job_id: int, limite: int = 300, db: Session = Depends(sessao)):
    _job(db, job_id)
    itens = list(db.scalars(select(BuscaLog).where(BuscaLog.job_id == job_id)
                            .order_by(BuscaLog.id.desc()).limit(min(limite, 2000))))
    return [{"momento": l.momento, "nivel": l.nivel, "mensagem": l.mensagem} for l in reversed(itens)]


@router.get("/eventos/stream")
async def stream(request: Request):
    item = barramento.assinar()
    _, fila = item

    async def gerar():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(fila.get(), timeout=15)
                    yield f"data: {json.dumps(ev, default=str, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            barramento.cancelar(item)

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
