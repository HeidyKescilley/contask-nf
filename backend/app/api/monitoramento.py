"""Painel de Monitoramento do uso: só o administrador do sistema (suporte do Contask).

Mostra métricas de produto (ativação, uso, frequência, retenção, pesquisa, experiência, erros e suporte)
e as gravações de sessão, que já chegam com todo texto e campo mascarados.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import monitoramento as m
from app.api.admin import exigir_admin
from app.api.uso import ler_gravacao
from app.core.db import sessao
from app.models import Gravacao, PedidoSuporte, Usuario

router = APIRouter(prefix="/api/admin/monitoramento", tags=["monitoramento"], dependencies=[Depends(exigir_admin)])

SECOES = {
    "ativacao": m.ativacao, "uso": m.uso, "frequencia": m.frequencia, "retencao": m.retencao,
    "pesquisa": m.pesquisa, "erros": m.erros, "suporte": m.suporte,
}


@router.get("/resumo")
def resumo(dias: int = Query(30, ge=1, le=365), db: Session = Depends(sessao)):
    b = m.Base(db, dias)
    return {"dias": dias, "gerado_em": b.agora, "desde": b.inicio,
            "eventos_desde": m._utc(b.eventos[0].momento) if b.eventos else None,
            **{k: f(b) for k, f in SECOES.items()}}


@router.get("/experiencia")
def experiencia(dias: int = Query(30, ge=1, le=365), rota: str | None = Query(None, max_length=120),
                db: Session = Depends(sessao)):
    return m.experiencia(m.Base(db, dias), rota)


@router.get("/gravacoes")
def gravacoes(dias: int = Query(30, ge=1, le=30), db: Session = Depends(sessao)):
    b = m.Base(db, dias)
    gs = list(db.scalars(select(Gravacao).where(Gravacao.iniciado_em >= b.inicio).order_by(Gravacao.iniciado_em.desc()).limit(300)))
    saida = []
    for g in gs:
        u = db.get(Usuario, g.usuario_id)
        ini, fim = m._utc(g.iniciado_em), m._utc(g.atualizado_em)
        saida.append({"id": g.id, "iniciado_em": ini, "duracao_s": int((fim - ini).total_seconds()) if fim and ini else 0,
                      "usuario": u.nome if u else "?", "escritorio": b.nome_esc(g.escritorio_id),
                      "paginas": g.paginas or [], "tamanho": g.tamanho})
    return saida


@router.get("/gravacoes/{gravacao_id}")
def gravacao(gravacao_id: int, db: Session = Depends(sessao)):
    g = db.get(Gravacao, gravacao_id)
    if g is None:
        raise HTTPException(404, "Gravação não encontrada (as gravações ficam 30 dias).")
    return {"id": g.id, "eventos": ler_gravacao(g)}


@router.put("/suporte/{pedido_id}")
def resolver(pedido_id: int, resolvido: bool = True, db: Session = Depends(sessao)):
    p = db.get(PedidoSuporte, pedido_id)
    if p is None:
        raise HTTPException(404, "Pedido não encontrado.")
    p.situacao = "resolvido" if resolvido else "aberto"
    p.resolvido_em = datetime.now(timezone.utc) if resolvido else None
    db.commit()
    return {"id": p.id, "situacao": p.situacao}
