"""Importação de empresas por planilha (XLSX ou CSV). Todas entram usando a procuração (certificado da contabilidade).

Fluxo: modelo -> prévia (só lê e valida) -> importar (cria as linhas válidas e agenda a busca inicial).
Colunas aceitas (cabeçalho em qualquer ordem): CNPJ (obrigatória), Razão social, Apelido.
Sem cabeçalho: A = CNPJ, B = Razão social, C = Apelido.
"""
from __future__ import annotations

import csv
import io
import re
import time
import unicodedata

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.uso import LimiteTeste, exigir_vaga_empresa
from app.core import brasilapi
from app.core.db import sessao
from app.fiscal.documentos import cnpj_valido, formatar_cnpj, limpar_cnpj
from app.jobs import acordar_fila
from app.jobs.fila import enfileirar
from app.models import Empresa

router = APIRouter(prefix="/api/importacao", tags=["importacao"])

MAX_LINHAS = 2000
MAX_BYTES = 5 * 1024 * 1024


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", t)


COLUNAS = {"cnpj": "cnpj", "razaosocial": "razao_social", "razao": "razao_social", "nome": "razao_social",
           "empresa": "razao_social", "nomeempresarial": "razao_social", "apelido": "apelido", "nomecurto": "apelido"}


def _cnpj_celula(v) -> str:
    """Excel guarda CNPJ numérico sem os zeros à esquerda: completa para 14 posições."""
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(int(v)).zfill(14)
    s = limpar_cnpj(str(v))
    return s.zfill(14) if s.isdigit() and 11 < len(s) < 14 else s


def _ler_linhas(nome: str, conteudo: bytes) -> list[list]:
    if nome.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            raise HTTPException(422, "Não foi possível ler a planilha. Envie um arquivo .xlsx válido ou .csv.") from None
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if nome.lower().endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                texto = conteudo.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        dialeto = ";" if texto.count(";") >= texto.count(",") else ","
        return [r for r in csv.reader(io.StringIO(texto), delimiter=dialeto)]
    raise HTTPException(422, "Formato não suportado. Use .xlsx ou .csv (baixe o modelo).")


def interpretar(nome: str, conteudo: bytes, db: Session) -> dict:
    linhas = [l for l in _ler_linhas(nome, conteudo) if any(str(c or "").strip() for c in l)]
    if not linhas:
        raise HTTPException(422, "A planilha está vazia.")
    mapa = {i: COLUNAS[_norm(c)] for i, c in enumerate(linhas[0]) if _norm(c) in COLUNAS}
    if "cnpj" in mapa.values():
        dados = linhas[1:]
    else:  # sem cabeçalho: A, B, C
        mapa, dados = {0: "cnpj", 1: "razao_social", 2: "apelido"}, linhas
    if len(dados) > MAX_LINHAS:
        raise HTTPException(422, f"A planilha tem {len(dados)} linhas; o limite é {MAX_LINHAS}.")
    existentes = {c: i for c, i in db.execute(select(Empresa.cnpj, Empresa.id))}
    vistos: set[str] = set()
    saida = []
    for n, linha in enumerate(dados, start=2 if dados is not linhas else 1):
        reg = {campo: linha[i] if i < len(linha) else None for i, campo in mapa.items()}
        cnpj = _cnpj_celula(reg.get("cnpj"))
        razao = str(reg.get("razao_social") or "").strip()
        apelido = str(reg.get("apelido") or "").strip()[:100] or None
        item = {"linha": n, "cnpj": cnpj, "cnpj_formatado": formatar_cnpj(cnpj), "razao_social": razao or None,
                "apelido": apelido, "situacao": "criar", "mensagem": None, "empresa_id": None}
        if not cnpj:
            item["situacao"], item["mensagem"] = "erro", "CNPJ em branco."
        elif not cnpj_valido(cnpj):
            item["situacao"], item["mensagem"] = "erro", "CNPJ inválido (dígitos verificadores)."
        elif cnpj in vistos:
            item["situacao"], item["mensagem"] = "repetida", "CNPJ repetido na planilha (vale a primeira linha)."
        elif cnpj in existentes:
            item["situacao"], item["mensagem"], item["empresa_id"] = "existente", "Já cadastrada.", existentes[cnpj]
        elif not razao:
            item["mensagem"] = "Sem razão social: será buscada na BrasilAPI."
        vistos.add(cnpj)
        saida.append(item)
    resumo = {k: sum(1 for i in saida if i["situacao"] == k) for k in ("criar", "existente", "repetida", "erro")}
    return {"linhas": saida, "resumo": resumo}


def _exigir_contabilidade(db: Session) -> Empresa:
    c = db.scalar(select(Empresa).where(Empresa.is_contabilidade))
    if c is None or c.certificado_id is None:
        raise HTTPException(409, "Cadastre primeiro a contabilidade e o certificado dela: as empresas importadas usam a procuração.")
    return c


@router.get("/empresas/modelo")
def modelo():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Empresas"
    ws.append(["CNPJ", "Razão social", "Apelido"])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.append(["00.000.000/0001-91", "EXEMPLO S.A. (apague esta linha)", "Exemplo"])
    for col, w in zip("ABC", (22, 52, 24)):
        ws.column_dimensions[col].width = w
    ws["A2"].number_format = "@"
    inst = wb.create_sheet("Instruções")
    for t in ("Preencha uma empresa por linha. Só o CNPJ é obrigatório.",
              "Sem razão social, o Contask NF busca na BrasilAPI.",
              "Todas as empresas importadas usam o certificado da contabilidade (procuração).",
              "Cada empresa precisa ter outorgado procuração eletrônica no e-CAC com o serviço da NFS-e.",
              "Formate a coluna CNPJ como Texto para o Excel não apagar os zeros à esquerda (o sistema completa se apagar)."):
        inst.append([t])
    inst.column_dimensions["A"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="modelo_importacao_empresas.xlsx"'})


@router.post("/empresas/previa")
async def previa(arquivo: UploadFile | None = File(None), db: Session = Depends(sessao)):
    if arquivo is None:
        raise HTTPException(422, "Selecione a planilha (.xlsx ou .csv).")
    conteudo = await arquivo.read()
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(422, "Arquivo grande demais (máximo 5 MB).")
    _exigir_contabilidade(db)
    return interpretar(arquivo.filename or "", conteudo, db)


class LinhaImportar(BaseModel):
    cnpj: str
    razao_social: str | None = None
    apelido: str | None = None


class PedidoImportar(BaseModel):
    linhas: list[LinhaImportar]


@router.post("/empresas")
def importar(pedido: PedidoImportar, db: Session = Depends(sessao)):
    _exigir_contabilidade(db)
    if len(pedido.linhas) > MAX_LINHAS:
        raise HTTPException(422, f"No máximo {MAX_LINHAS} empresas por importação.")
    novas = {_cnpj_celula(l.cnpj) for l in pedido.linhas}
    novas = [c for c in novas if cnpj_valido(c) and not db.scalar(select(Empresa.id).where(Empresa.cnpj == c))]
    try:
        exigir_vaga_empresa(db, len(novas))
    except LimiteTeste as erro:
        raise HTTPException(403, str(erro)) from None
    resultado = []
    for l in pedido.linhas:
        cnpj = _cnpj_celula(l.cnpj)
        r = {"cnpj": cnpj, "cnpj_formatado": formatar_cnpj(cnpj), "razao_social": l.razao_social, "situacao": "criada",
             "mensagem": None, "empresa_id": None}
        if not cnpj_valido(cnpj):
            r["situacao"], r["mensagem"] = "erro", "CNPJ inválido."
            resultado.append(r)
            continue
        ja = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
        if ja is not None:
            r["situacao"], r["mensagem"], r["empresa_id"] = "existente", "Já cadastrada.", ja.id
            resultado.append(r)
            continue
        e = Empresa(cnpj=cnpj, razao_social=(l.razao_social or "").strip(), apelido=(l.apelido or "").strip() or None,
                    modo_certificado="contabilidade", is_contabilidade=False, ativa=True)
        if not e.razao_social:
            try:
                d = brasilapi.consultar(cnpj)
                e.razao_social, e.nome_fantasia = d["razao_social"], d["nome_fantasia"]
                e.uf, e.municipio, e.situacao_cadastral, e.dados_brasilapi = d["uf"], d["municipio"], d["situacao_cadastral"], d["bruto"]
                time.sleep(0.3)  # gentileza com a API pública
            except brasilapi.BrasilApiErro as ex:
                r["situacao"], r["mensagem"] = "erro", f"Sem razão social na planilha e a BrasilAPI falhou: {ex}"
                resultado.append(r)
                continue
            if not e.razao_social:
                r["situacao"], r["mensagem"] = "erro", "Sem razão social na planilha nem na BrasilAPI."
                resultado.append(r)
                continue
        db.add(e)
        db.flush()
        enfileirar(db, e.id, "inicial")
        db.commit()
        r["empresa_id"], r["razao_social"] = e.id, e.razao_social
        resultado.append(r)
    acordar_fila()
    resumo = {k: sum(1 for i in resultado if i["situacao"] == k) for k in ("criada", "existente", "erro")}
    return {"linhas": resultado, "resumo": resumo}
