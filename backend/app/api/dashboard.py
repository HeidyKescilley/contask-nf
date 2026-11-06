"""Dashboard mensal. O mês é por COMPETÊNCIA (decisão 2 do plano: referência fiscal).

- Total de NFS-e: notas com competência no mês (qualquer papel e status).
- Total de XMLs: essas notas + eventos registrados no mês (data do evento).
- Valores em R$ somam só notas Autorizadas; canceladas e rejeitadas têm cards próprios.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.escopo import escritorio_atual, obter_empresa
from app.core.db import sessao
from app.models import EventoNota, Nota

router = APIRouter(prefix="/api", tags=["dashboard"])


def _limites(ano: int, mes: int) -> tuple[date, date]:
    ini = date(ano, mes, 1)
    fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    return ini, fim


def _desloca(ano: int, mes: int, n: int) -> tuple[int, int]:
    t = ano * 12 + (mes - 1) + n
    return t // 12, t % 12 + 1


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


@router.get("/empresas/{empresa_id}/dashboard")
def dashboard(empresa_id: int, mes: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(sessao),
              esc: int = Depends(escritorio_atual)):
    obter_empresa(db, empresa_id, esc)
    hoje = date.today()
    ano, m = (int(mes[:4]), int(mes[5:])) if mes else (hoje.year, hoje.month)
    if not 1 <= m <= 12:
        raise HTTPException(422, "Mês inválido.")
    ini, fim = _limites(ano, m)
    no_mes = (Nota.empresa_id == empresa_id, Nota.competencia >= ini, Nota.competencia < fim)

    # Por papel e status no mês
    linhas = db.execute(
        select(Nota.papel, Nota.status, func.count(), func.coalesce(func.sum(Nota.valor_servico), 0))
        .where(*no_mes).group_by(Nota.papel, Nota.status)).all()
    agg: dict[tuple[str, str], tuple[int, Decimal]] = {(p, s): (q, _dec(v)) for p, s, q, v in linhas}

    def soma(papel: str | None, status: str) -> dict:
        q, v = 0, Decimal("0.00")
        for (p, s), (qq, vv) in agg.items():
            if s == status and (papel is None or p == papel):
                q, v = q + qq, v + vv
        return {"quantidade": q, "valor": v}

    total_nfse = sum(q for q, _ in agg.values())
    eventos_mes = db.scalar(select(func.count()).select_from(EventoNota).where(
        EventoNota.empresa_id == empresa_id,
        EventoNota.data_evento >= datetime.combine(ini, datetime.min.time()),
        EventoNota.data_evento < datetime.combine(fim, datetime.min.time()))) or 0
    em_analise = db.scalar(select(func.count()).select_from(Nota).where(*no_mes, Nota.em_analise_fiscal)) or 0

    # Série dos últimos 6 meses (autorizadas), por papel
    a6, m6 = _desloca(ano, m, -5)
    ini6, _ = _limites(a6, m6)
    mes_expr = func.strftime("%Y-%m", Nota.competencia)
    serie_db = db.execute(
        select(Nota.papel, mes_expr, func.count(), func.coalesce(func.sum(Nota.valor_servico), 0))
        .where(Nota.empresa_id == empresa_id, Nota.status == "autorizada", Nota.competencia >= ini6, Nota.competencia < fim,
               Nota.papel.in_(["prestada", "tomada"]))
        .group_by(Nota.papel, mes_expr)).all()
    meses = [f"{a:04d}-{mm:02d}" for a, mm in (_desloca(ano, m, k) for k in range(-5, 1))]
    serie = {p: {mm: {"mes": mm, "quantidade": 0, "valor": Decimal("0.00")} for mm in meses} for p in ("prestada", "tomada")}
    for p, mm, q, v in serie_db:
        serie[p][mm] = {"mes": mm, "quantidade": q, "valor": _dec(v)}

    # Último mês com notas (para sugerir quando o mês escolhido está vazio)
    ultimo = db.scalar(select(func.max(Nota.competencia)).where(Nota.empresa_id == empresa_id))

    def bloco(papel: str) -> dict:
        aut = soma(papel, "autorizada")
        return {**aut, "canceladas": soma(papel, "cancelada")["quantidade"], "rejeitadas": soma(papel, "rejeitada")["quantidade"],
                "serie": list(serie[papel].values())}

    canc, rej = soma(None, "cancelada"), soma(None, "rejeitada")
    return {
        "mes": f"{ano:04d}-{m:02d}", "base": "competencia", "inicio": ini.isoformat(),
        "fim": date.fromordinal(fim.toordinal() - 1).isoformat(),
        "total_xmls": total_nfse + eventos_mes, "total_nfse": total_nfse, "eventos_mes": eventos_mes,
        "valor_autorizado": soma(None, "autorizada")["valor"],
        "prestados": bloco("prestada"), "tomados": bloco("tomada"),
        "canceladas": {**canc, "prestadas": soma("prestada", "cancelada")["quantidade"], "tomadas": soma("tomada", "cancelada")["quantidade"]},
        "rejeitadas": {**rej, "prestadas": soma("prestada", "rejeitada")["quantidade"], "tomadas": soma("tomada", "rejeitada")["quantidade"]},
        "em_analise": em_analise,
        "outras": sum(q for (p, _), (q, _) in agg.items() if p not in ("prestada", "tomada")),
        "ultimo_mes_com_notas": ultimo.strftime("%Y-%m") if ultimo else None,
    }
