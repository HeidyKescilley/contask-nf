"""Notas: lista com filtros e paginação no servidor, detalhes com eventos, XML e DANFSe (PDF)."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import Integer, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.core.db import sessao
from app.fiscal.danfse import gerar_danfse
from app.fiscal.parser import XmlInvalido
from app.fiscal.status import CONHECIDOS, DESCRICOES
from app.models import Empresa, EventoNota, Nota

router = APIRouter(prefix="/api", tags=["notas"])

def interpretar_valor(q: str) -> Decimal | None:
    """Aceita '1.234,56', '1234,56', 'R$ 1.234,56', '1234.56' e '1234'."""
    s = q.strip().replace("R$", "").replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    if "," in s:
        if s.count(",") > 1 or not re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{1,2}|\d+,\d{1,2}", s):
            return None
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        if re.fullmatch(r"\d+\.\d{1,2}", s):
            pass  # 1234.56
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")  # 1.234 (milhar)
        else:
            return None
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _filtro_busca(q: str):
    q = q.strip()
    digitos = re.sub(r"\D", "", q)
    conds = []
    if re.fullmatch(r"\d{50}", digitos) and digitos == q.replace(" ", ""):
        return Nota.chave == digitos
    if digitos and len(digitos) >= 20 and digitos == q.replace(" ", ""):
        return Nota.chave.like(f"%{digitos}%")
    valor = interpretar_valor(q)
    if valor is not None:
        conds += [Nota.valor_servico == valor, Nota.valor_liquido == valor]
    if q.isdigit() and len(q) <= 15:
        conds.append(Nota.numero.in_({q, q.lstrip("0") or "0"}))
    if not q.replace(",", "").replace(".", "").isdigit():
        termo = f"%{q}%"
        conds += [Nota.emitente_nome.ilike(termo), Nota.tomador_nome.ilike(termo)]
        doc = re.sub(r"[^0-9A-Za-z]", "", q)
        if len(doc) >= 8 and re.search(r"\d{4}", doc):
            conds += [Nota.emitente_doc.like(f"%{doc}%"), Nota.tomador_doc.like(f"%{doc}%"), Nota.prestador_doc.like(f"%{doc}%")]
    elif len(digitos) >= 8:
        conds += [Nota.emitente_doc.like(f"%{digitos}%"), Nota.tomador_doc.like(f"%{digitos}%")]
    return or_(*conds) if conds else Nota.id == -1


def _data(v: str | None, nome: str) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise HTTPException(422, f"Data inválida em {nome}: use AAAA-MM-DD.") from None


def filtros_notas(empresa_id: int, papel: str | None, q: str | None, inicio: str | None, fim: str | None,
                  campo_data: str, status: str | None) -> list:
    conds = [Nota.empresa_id == empresa_id]
    if papel and papel != "todas":
        if papel not in ("prestada", "tomada", "intermediada", "outra"):
            raise HTTPException(422, "Papel inválido.")
        conds.append(Nota.papel == papel)
    if status and status != "todas":
        if status not in ("autorizada", "cancelada", "rejeitada"):
            raise HTTPException(422, "Status inválido.")
        conds.append(Nota.status == status)
    ini, fi = _data(inicio, "início"), _data(fim, "fim")
    if ini and fi and ini > fi:
        raise HTTPException(422, "A data inicial é maior que a final.")
    if campo_data == "competencia":
        if ini:
            conds.append(Nota.competencia >= ini)
        if fi:
            conds.append(Nota.competencia <= fi)
    else:
        # data_emissao é gravada com o horário local do XML: compara pelo dia
        if ini:
            conds.append(Nota.data_emissao >= datetime.combine(ini, datetime.min.time()))
        if fi:
            conds.append(Nota.data_emissao < datetime.combine(fi + timedelta(days=1), datetime.min.time()))
    if q and q.strip():
        conds.append(_filtro_busca(q))
    return conds


def nota_resumo(n: Nota) -> dict:
    return {
        "id": n.id, "chave": n.chave, "papel": n.papel, "numero": n.numero, "serie": n.serie,
        "emitente_doc": n.emitente_doc, "emitente_nome": n.emitente_nome, "emitente_uf": n.emitente_uf,
        "prestador_doc": n.prestador_doc, "tomador_doc": n.tomador_doc, "tomador_nome": n.tomador_nome,
        "valor_servico": n.valor_servico, "valor_liquido": n.valor_liquido, "valor_iss": n.valor_iss,
        "data_emissao": n.data_emissao.isoformat() if n.data_emissao else None,
        "competencia": n.competencia, "municipio": n.municipio, "status": n.status, "status_detalhe": n.status_detalhe,
        "em_analise_fiscal": n.em_analise_fiscal, "bloqueada": n.bloqueada,
    }


@router.get("/empresas/{empresa_id}/notas")
def listar_notas(
    empresa_id: int, papel: str | None = None, q: str | None = None, inicio: str | None = None, fim: str | None = None,
    campo_data: str = Query("emissao", pattern="^(emissao|competencia)$"), status: str | None = None,
    page: int = Query(1, ge=1), limite: int = Query(50, ge=1, le=200),
    ordem: str = Query("emissao_desc", pattern="^(emissao_desc|emissao|valor_desc|valor|numero_desc|numero)$"),
    db: Session = Depends(sessao),
):
    if db.get(Empresa, empresa_id) is None:
        raise HTTPException(404, "Empresa não encontrada.")
    conds = filtros_notas(empresa_id, papel, q, inicio, fim, campo_data, status)
    onde = and_(*conds)
    total, soma_aut = db.execute(
        select(func.count(Nota.id),
               func.coalesce(func.sum(func.iif(Nota.status == "autorizada", Nota.valor_servico, 0)), 0))
        .where(onde)).one()
    por_status = dict(db.execute(select(Nota.status, func.count()).where(onde).group_by(Nota.status)).all())
    numero_int = cast(Nota.numero, Integer)
    ordens = {
        "emissao_desc": (Nota.data_emissao.desc(), Nota.id.desc()), "emissao": (Nota.data_emissao.asc(), Nota.id.asc()),
        "valor_desc": (Nota.valor_servico.desc(), Nota.id.desc()), "valor": (Nota.valor_servico.asc(), Nota.id.asc()),
        "numero_desc": (numero_int.desc(), Nota.id.desc()), "numero": (numero_int.asc(), Nota.id.asc()),
    }[ordem]
    itens = db.scalars(select(Nota).where(onde).order_by(*ordens).offset((page - 1) * limite).limit(limite)).all()
    return {
        "itens": [nota_resumo(n) for n in itens], "total": total, "pagina": page, "limite": limite,
        "paginas": max(1, -(-total // limite)),
        "totais": {"valor_autorizado": Decimal(str(soma_aut)).quantize(Decimal("0.01")),
                   "autorizadas": por_status.get("autorizada", 0), "canceladas": por_status.get("cancelada", 0),
                   "rejeitadas": por_status.get("rejeitada", 0)},
    }


def _nota(db: Session, nota_id: int) -> Nota:
    n = db.get(Nota, nota_id)
    if n is None:
        raise HTTPException(404, "Nota não encontrada.")
    return n


@router.get("/notas/{nota_id}")
def detalhe_nota(nota_id: int, db: Session = Depends(sessao)):
    n = _nota(db, nota_id)
    eventos = db.scalars(select(EventoNota).where(EventoNota.empresa_id == n.empresa_id, EventoNota.chave == n.chave)
                         .order_by(EventoNota.data_evento, EventoNota.nsu)).all()
    return {
        **nota_resumo(n), "n_dps": n.n_dps, "c_stat": n.c_stat, "nsu": n.nsu, "empresa_id": n.empresa_id,
        "eventos": [{"codigo": e.codigo, "descricao": DESCRICOES.get(e.codigo or "") or e.descricao or "Evento não classificado",
                     "conhecido": e.codigo in CONHECIDOS, "data_evento": e.data_evento, "nsu": e.nsu} for e in eventos],
    }


def _arquivo_xml(n: Nota) -> Path:
    if not n.xml_path:
        raise HTTPException(404, "O XML desta nota não está no computador. Rode a busca de novo.")
    p = config().dados_dir / n.xml_path
    if not p.is_file():
        raise HTTPException(404, "O arquivo XML não foi encontrado na pasta de dados. Rode \"Refazer do zero\" para baixá-lo de novo.")
    return p


@router.get("/notas/{nota_id}/xml")
def baixar_xml(nota_id: int, db: Session = Depends(sessao)):
    n = _nota(db, nota_id)
    return FileResponse(_arquivo_xml(n), media_type="application/xml", filename=f"{n.chave}.xml")


def marca_dagua(n: Nota) -> str | None:
    if n.status != "cancelada":
        return None
    return "SUBSTITUÍDA" if (n.status_detalhe or "").lower().find("substitui") >= 0 else "CANCELADA"


@router.get("/notas/{nota_id}/pdf")
def danfse(nota_id: int, download: int = 0, db: Session = Depends(sessao)):
    """DANFSe gerado localmente a partir do XML (NT 008/2026), guardado para os próximos acessos."""
    n = _nota(db, nota_id)
    xml_path = _arquivo_xml(n)
    marca = marca_dagua(n)
    sufixo = "" if marca is None else ("-substituida" if marca == "SUBSTITUÍDA" else "-cancelada")
    mes = xml_path.parent.name
    empresa = db.get(Empresa, n.empresa_id)
    destino = config().dados_dir / "empresas" / empresa.cnpj / "pdf" / mes / f"{n.chave}{sufixo}.pdf"
    if not destino.is_file():
        try:
            pdf = gerar_danfse(xml_path.read_bytes(), marca_dagua=marca)
        except XmlInvalido as e:
            raise HTTPException(422, f"Não foi possível gerar o DANFSe: XML inválido ({e}).") from None
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        tmp.write_bytes(pdf)
        os.replace(tmp, destino)
        rel = destino.relative_to(config().dados_dir).as_posix()
        if n.pdf_path != rel:
            n.pdf_path = rel
            db.commit()
    disp = "attachment" if download else "inline"
    return Response(destino.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="DANFSe_{n.numero or n.chave}_{n.chave}.pdf"',
                             "Cache-Control": "no-cache"})
