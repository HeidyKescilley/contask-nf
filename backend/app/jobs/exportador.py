"""Exportação: ZIP com XMLs (notas e, opcionalmente, eventos) + relatório XLSX ou PDF.

Estrutura do ZIP:
    prestados/xml/<chave>.xml
    tomados/xml/<chave>.xml
    eventos/<chave>_<codigo>_<nsu>.xml      (opcional)
    relatorio.xlsx | relatorio.pdf

A prévia e o ZIP usam a MESMA seleção (selecionar_notas), então a quantidade bate por construção;
um XML ausente no disco é listado no relatório em vez de sumir em silêncio.
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, model_validator
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.notas import filtros_notas
from app.core.config import config
from app.fiscal.status import DESCRICOES
from app.models import DocumentoDfe, Empresa, EventoNota, Exportacao, Nota
from .barramento import barramento

log = logging.getLogger("contask.exportacao")

PAPEIS = {"prestados": ["prestada"], "tomados": ["tomada"], "ambos": ["prestada", "tomada"]}
PASTA = {"prestada": "prestados", "tomada": "tomados"}
ROTULO_STATUS = {"autorizada": "Autorizada", "cancelada": "Cancelada", "rejeitada": "Rejeitada"}


class Filtros(BaseModel):
    tipo: Literal["prestados", "tomados", "ambos"] = "ambos"
    inicio: date | None = None
    fim: date | None = None
    campo_data: Literal["competencia", "emissao"] = "competencia"
    status: Literal["todas", "autorizada", "cancelada", "rejeitada"] = "autorizada"
    relatorio: Literal["xlsx", "pdf"] = "xlsx"
    incluir_xml: bool = True
    incluir_eventos: bool = False
    escopo: Literal["empresa", "todas"] = "empresa"  # "todas": um ZIP com uma pasta por empresa ativa

    @model_validator(mode="after")
    def _periodo(self):
        if self.inicio and self.fim and self.inicio > self.fim:
            raise ValueError("A data inicial é maior que a final.")
        return self

    def descricao(self) -> list[tuple[str, str]]:
        f = lambda d: d.strftime("%d/%m/%Y") if d else "—"  # noqa: E731
        return ([("Empresas", "Todas as empresas ativas (uma pasta por empresa)")] if self.escopo == "todas" else []) + [
            ("Tipo", {"prestados": "Prestados (saídas)", "tomados": "Tomados (entradas)", "ambos": "Prestados e tomados"}[self.tipo]),
            ("Período", f"{f(self.inicio)} a {f(self.fim)}" if (self.inicio or self.fim) else "Todo o período"),
            ("Data usada", "Competência" if self.campo_data == "competencia" else "Emissão"),
            ("Status", {"todas": "Todas (inclui canceladas e rejeitadas)", "autorizada": "Autorizadas",
                        "cancelada": "Canceladas", "rejeitada": "Rejeitadas"}[self.status]),
            ("Conteúdo", ", ".join(x for x in ("XMLs das notas" if self.incluir_xml else "",
                                              "XMLs dos eventos" if self.incluir_eventos else "") if x) or "Só o relatório"),
        ]


def selecionar_notas(db: Session, empresa_id: int, f: Filtros) -> list[Nota]:
    notas: list[Nota] = []
    for papel in PAPEIS[f.tipo]:
        conds = filtros_notas(empresa_id, papel, None, f.inicio.isoformat() if f.inicio else None,
                              f.fim.isoformat() if f.fim else None, f.campo_data, None if f.status == "todas" else f.status)
        notas += db.scalars(select(Nota).where(and_(*conds)).order_by(Nota.data_emissao, Nota.id)).all()
    return notas


def selecionar_eventos(db: Session, empresa_id: int, chaves: set[str]) -> list[EventoNota]:
    if not chaves:
        return []
    saida = []
    lista = list(chaves)
    for i in range(0, len(lista), 900):  # limite de parâmetros do SQLite
        saida += db.scalars(select(EventoNota).where(EventoNota.empresa_id == empresa_id,
                                                     EventoNota.chave.in_(lista[i:i + 900]))).all()
    return sorted(saida, key=lambda e: (e.chave, e.nsu or 0))


def empresas_do_escopo(db: Session, empresa_id: int, f: Filtros) -> list[Empresa]:
    if f.escopo == "todas":
        return list(db.scalars(select(Empresa).where(Empresa.ativa).order_by(Empresa.razao_social)))
    e = db.get(Empresa, empresa_id)
    return [e] if e else []


def _previa_empresa(db: Session, empresa_id: int, f: Filtros) -> dict:
    notas = selecionar_notas(db, empresa_id, f)
    por_status = {s: {"quantidade": 0, "valor": Decimal("0.00")} for s in ROTULO_STATUS}
    for n in notas:
        por_status[n.status]["quantidade"] += 1
        por_status[n.status]["valor"] += n.valor_servico or Decimal(0)
    eventos = len(selecionar_eventos(db, empresa_id, {n.chave for n in notas})) if f.incluir_eventos else 0
    return {
        "total": len(notas),
        "prestadas": sum(1 for n in notas if n.papel == "prestada"),
        "tomadas": sum(1 for n in notas if n.papel == "tomada"),
        "por_status": por_status,
        "eventos": eventos,
        "arquivos_xml": (len(notas) if f.incluir_xml else 0) + eventos,
    }


def previa(db: Session, empresa_id: int, f: Filtros) -> dict:
    """Prévia da empresa ou, no escopo "todas", a soma de todas + o detalhe por empresa."""
    if f.escopo != "todas":
        return _previa_empresa(db, empresa_id, f)
    total = {"total": 0, "prestadas": 0, "tomadas": 0, "eventos": 0, "arquivos_xml": 0,
             "por_status": {s: {"quantidade": 0, "valor": Decimal("0.00")} for s in ROTULO_STATUS}, "empresas": []}
    for e in empresas_do_escopo(db, empresa_id, f):
        p = _previa_empresa(db, e.id, f)
        for k in ("total", "prestadas", "tomadas", "eventos", "arquivos_xml"):
            total[k] += p[k]
        for st, v in p["por_status"].items():
            total["por_status"][st]["quantidade"] += v["quantidade"]
            total["por_status"][st]["valor"] += v["valor"]
        total["empresas"].append({"id": e.id, "cnpj": e.cnpj, "nome": e.apelido or e.razao_social, "pasta": pasta_empresa(e),
                                  "total": p["total"], "arquivos_xml": p["arquivos_xml"],
                                  "valor_autorizado": p["por_status"]["autorizada"]["valor"]})
    total["empresas_com_notas"] = sum(1 for x in total["empresas"] if x["total"])
    return total


_PROIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def pasta_empresa(e: Empresa) -> str:
    """Pasta da empresa no ZIP: CNPJ seguido do nome (válido no Windows)."""
    nome = _PROIBIDOS.sub(" ", e.razao_social or "")
    nome = re.sub(r"\s+", " ", nome).strip().rstrip(".")[:80].rstrip(" .")
    return f"{e.cnpj} {nome}".strip()


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:40] or "empresa"


def nome_arquivo(e: Empresa | None, f: Filtros) -> str:
    ini = f.inicio.isoformat() if f.inicio else "inicio"
    fim = f.fim.isoformat() if f.fim else "hoje"
    quem = "Todas_as_empresas" if f.escopo == "todas" or e is None else _slug(e.apelido or e.nome_fantasia or e.razao_social)
    return f"Contask_NF_{quem}_{ini}_a_{fim}.zip"


# --- Relatórios ---------------------------------------------------------------------------------

COLUNAS = ["Papel", "Número", "Série", "Chave de acesso", "Emissão", "Competência", "Emitente (CNPJ/CPF)", "Emitente",
           "Tomador (CNPJ/CPF)", "Tomador", "Valor do serviço", "Valor líquido", "ISSQN", "Status", "Detalhe do status"]


def _linha(n: Nota) -> list:
    return ["Prestada" if n.papel == "prestada" else "Tomada", n.numero, n.serie, n.chave,
            n.data_emissao.replace(tzinfo=None) if n.data_emissao else None, n.competencia,
            n.emitente_doc, n.emitente_nome, n.tomador_doc, n.tomador_nome,
            n.valor_servico, n.valor_liquido, n.valor_iss, ROTULO_STATUS.get(n.status, n.status), n.status_detalhe]


@dataclass
class Resumo:
    empresa: Empresa
    filtros: Filtros
    gerado_em: datetime
    notas: list[Nota]
    eventos: list[EventoNota]
    xml_no_zip: int
    ausentes: list[str] = field(default_factory=list)

    def por_status(self) -> list[tuple[str, int, Decimal]]:
        out = []
        for s, rot in ROTULO_STATUS.items():
            sel = [n for n in self.notas if n.status == s]
            out.append((rot, len(sel), sum((n.valor_servico or Decimal(0) for n in sel), Decimal("0.00"))))
        return out


def relatorio_xlsx(r: Resumo) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    negrito = Font(bold=True)
    ws.append(["Contask NF · Exportação de NFS-e"]); ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"{r.empresa.razao_social} · CNPJ {r.empresa.cnpj}"])
    ws.append([f"Gerado em {r.gerado_em.astimezone().strftime('%d/%m/%Y %H:%M:%S')}"])
    ws.append([])
    ws.append(["Filtros usados"]); ws.cell(ws.max_row, 1).font = negrito
    for k, v in r.filtros.descricao():
        ws.append([k, v])
    ws.append([])
    ws.append(["Totais por status", "Quantidade", "Valor do serviço"])
    for c in ws[ws.max_row]:
        c.font = negrito
    for rot, q, v in r.por_status():
        ws.append([rot, q, v]); ws.cell(ws.max_row, 3).number_format = '"R$" #,##0.00'
    ws.append(["Total", len(r.notas), sum((v for _, _, v in r.por_status()), Decimal("0.00"))])
    ws.cell(ws.max_row, 1).font = negrito; ws.cell(ws.max_row, 3).number_format = '"R$" #,##0.00'
    ws.append([])
    ws.append(["Arquivos XML no ZIP", r.xml_no_zip])
    ws.append(["Eventos incluídos", len(r.eventos) if r.filtros.incluir_eventos else 0])
    if r.ausentes:
        ws.append(["XMLs não encontrados no computador", len(r.ausentes)])
        for ch in r.ausentes:
            ws.append(["", ch])
    ws.column_dimensions["A"].width = 34; ws.column_dimensions["B"].width = 44; ws.column_dimensions["C"].width = 20

    wn = wb.create_sheet("Notas")
    wn.append(COLUNAS)
    cinza = PatternFill("solid", start_color="FFF2F2F2")
    for c in wn[1]:
        c.font, c.fill, c.alignment = negrito, cinza, Alignment(vertical="center")
    for n in r.notas:
        wn.append(_linha(n))
    larguras = [10, 10, 8, 54, 17, 12, 20, 40, 20, 40, 15, 15, 12, 12, 34]
    for i, w in enumerate(larguras, start=1):
        wn.column_dimensions[get_column_letter(i)].width = w
    for row in wn.iter_rows(min_row=2):
        row[4].number_format = "dd/mm/yyyy hh:mm"
        row[5].number_format = "dd/mm/yyyy"
        for c in row[10:13]:
            c.number_format = '"R$" #,##0.00'
    wn.freeze_panes = "A2"
    wn.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS))}{max(wn.max_row, 1)}"

    if r.filtros.incluir_eventos and r.eventos:
        we = wb.create_sheet("Eventos")
        we.append(["Chave de acesso", "Código", "Evento", "Data", "NSU"])
        for c in we[1]:
            c.font, c.fill = negrito, cinza
        for e in r.eventos:
            we.append([e.chave, e.codigo, DESCRICOES.get(e.codigo or "") or e.descricao,
                       e.data_evento.replace(tzinfo=None) if e.data_evento else None, e.nsu])
            we.cell(we.max_row, 4).number_format = "dd/mm/yyyy hh:mm"
        for col, w in zip("ABCDE", (54, 9, 46, 17, 10)):
            we.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def relatorio_pdf(r: Resumo) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def moeda(v) -> str:
        if v is None:
            return "—"
        return "R$ " + f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    est = getSampleStyleSheet()
    pequeno = est["BodyText"].clone("p", fontSize=7, leading=8.5)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm,
                            bottomMargin=1 * cm, title="Relatório de NFS-e", author="Contask NF")
    hist = [Paragraph("Relatório de NFS-e", est["Title"]),
            Paragraph(f"{r.empresa.razao_social} · CNPJ {r.empresa.cnpj} · gerado em {r.gerado_em.astimezone():%d/%m/%Y %H:%M:%S}", est["BodyText"]),
            Spacer(1, 6)]
    estilo_tab = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                             ("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")])
    filtros = Table([["Filtro", "Valor"]] + [list(x) for x in r.filtros.descricao()], colWidths=[4 * cm, 12 * cm])
    filtros.setStyle(estilo_tab)
    totais = Table([["Status", "Quantidade", "Valor do serviço"]] + [[a, str(b), moeda(c)] for a, b, c in r.por_status()]
                   + [["Total", str(len(r.notas)), moeda(sum((v for _, _, v in r.por_status()), Decimal(0)))],
                      ["Arquivos XML no ZIP", str(r.xml_no_zip), ""]], colWidths=[5 * cm, 3 * cm, 4 * cm])
    totais.setStyle(estilo_tab)
    hist += [filtros, Spacer(1, 6), totais, Spacer(1, 10)]
    if r.ausentes:
        hist.append(Paragraph(f"XMLs não encontrados no computador ({len(r.ausentes)}): " + ", ".join(r.ausentes), pequeno))
        hist.append(Spacer(1, 6))
    dados = [["Papel", "Nº / Série", "Emissão", "Compet.", "Emitente", "Tomador", "Valor", "Status", "Chave"]]
    for n in r.notas:
        dados.append(["Prestada" if n.papel == "prestada" else "Tomada", f"{n.numero or '—'} / {n.serie or '—'}",
                      n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else "—",
                      n.competencia.strftime("%m/%Y") if n.competencia else "—",
                      Paragraph(f"{n.emitente_nome or '—'}<br/>{n.emitente_doc or ''}", pequeno),
                      Paragraph(f"{n.tomador_nome or 'Não informado'}<br/>{n.tomador_doc or ''}", pequeno),
                      moeda(n.valor_servico), ROTULO_STATUS.get(n.status, n.status), Paragraph(n.chave, pequeno)])
    tab = Table(dados, repeatRows=1, colWidths=[1.6 * cm, 2.3 * cm, 1.8 * cm, 1.4 * cm, 5.4 * cm, 5.4 * cm, 2.4 * cm, 1.8 * cm, 5.6 * cm])
    tab.setStyle(TableStyle(estilo_tab.getCommands() + [("FONTSIZE", (0, 1), (-1, -1), 7), ("ALIGN", (6, 1), (6, -1), "RIGHT")]))
    hist.append(tab)

    def rodape(c, d):
        c.setFont("Helvetica", 7)
        c.drawRightString(landscape(A4)[0] - 1 * cm, 0.6 * cm, f"Página {d.page}")

    doc.build(hist, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()


# --- Geração -------------------------------------------------------------------------------------

def _escrever_empresa(z: zipfile.ZipFile, db: Session, empresa: Empresa, f: Filtros, prefixo: str,
                      gerado_em: datetime) -> Resumo:
    """Escreve no ZIP os XMLs e o relatório de uma empresa sob `prefixo` ("" ou "<pasta>/")."""
    dados = config().dados_dir
    notas = selecionar_notas(db, empresa.id, f)
    eventos = selecionar_eventos(db, empresa.id, {n.chave for n in notas}) if f.incluir_eventos else []
    ausentes: list[str] = []
    no_zip = 0
    if f.incluir_xml:
        for n in notas:
            p = dados / n.xml_path if n.xml_path else None
            if p is None or not p.is_file():
                ausentes.append(n.chave)
                continue
            z.write(p, f"{prefixo}{PASTA.get(n.papel, 'outras')}/xml/{n.chave}.xml")
            no_zip += 1
    for e in eventos:
        doc = db.get(DocumentoDfe, e.documento_id) if e.documento_id else None
        p = dados / doc.xml_path if doc and doc.xml_path else None
        if p is None or not p.is_file():
            ausentes.append(f"{e.chave} (evento NSU {e.nsu})")
            continue
        z.write(p, f"{prefixo}eventos/{e.chave}_{e.codigo or 'evento'}_{e.nsu}.xml")
        no_zip += 1
    r = Resumo(empresa=empresa, filtros=f, gerado_em=gerado_em, notas=notas, eventos=eventos,
               xml_no_zip=no_zip, ausentes=ausentes)
    if f.relatorio == "xlsx":
        z.writestr(f"{prefixo}relatorio.xlsx", relatorio_xlsx(r))
    else:
        z.writestr(f"{prefixo}relatorio.pdf", relatorio_pdf(r))
    return r


def _linha_resumo(r: Resumo) -> list:
    st = {rot: (q, v) for rot, q, v in r.por_status()}
    return [len(r.notas), sum(n.papel == "prestada" for n in r.notas), sum(n.papel == "tomada" for n in r.notas),
            st["Autorizada"][0], st["Autorizada"][1], st["Cancelada"][0], st["Rejeitada"][0], r.xml_no_zip, len(r.ausentes)]


def resumo_empresas_xlsx(resumos: list[Resumo], f: Filtros, gerado_em: datetime) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Empresas"
    ws.append(["Contask NF · Exportação de todas as empresas"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Gerado em {gerado_em.astimezone().strftime('%d/%m/%Y %H:%M:%S')}"])
    ws.append([])
    for k, v in f.descricao():
        ws.append([k, v])
    ws.append([])
    ws.append(["Pasta no ZIP", "CNPJ", "Razão social", "Notas", "Prestadas", "Tomadas", "Autorizadas", "Valor autorizado",
               "Canceladas", "Rejeitadas", "XMLs no ZIP", "XMLs ausentes"])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    tot = [0] * 9
    for r in resumos:
        linha = _linha_resumo(r)
        ws.append([pasta_empresa(r.empresa) if r.notas else "(sem notas no filtro)", r.empresa.cnpj, r.empresa.razao_social] + linha)
        ws.cell(ws.max_row, 8).number_format = '"R$" #,##0.00'
        tot = [a + b for a, b in zip(tot, linha)]
    ws.append(["Total", "", f"{len(resumos)} empresa(s)"] + tot)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ws.cell(ws.max_row, 8).number_format = '"R$" #,##0.00'
    for col, w in zip("ABCDEFGHIJKL", (62, 16, 46, 9, 10, 9, 11, 17, 11, 11, 12, 13)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def resumo_empresas_pdf(resumos: list[Resumo], f: Filtros, gerado_em: datetime) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def moeda(v) -> str:
        return "R$ " + f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    est = getSampleStyleSheet()
    pequeno = est["BodyText"].clone("p", fontSize=7, leading=8.5)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm,
                            bottomMargin=1 * cm, title="Exportação de todas as empresas", author="Contask NF")
    estilo = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                         ("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                         ("VALIGN", (0, 0), (-1, -1), "TOP")])
    filtros = Table([["Filtro", "Valor"]] + [list(x) for x in f.descricao()], colWidths=[4 * cm, 14 * cm])
    filtros.setStyle(estilo)
    linhas = [["Empresa (pasta no ZIP)", "Notas", "Autorizadas", "Valor autorizado", "Canceladas", "Rejeitadas", "XMLs no ZIP"]]
    for r in resumos:
        q, _, _, aut, v, canc, rej, xml, _ = _linha_resumo(r)
        linhas.append([Paragraph(pasta_empresa(r.empresa), pequeno), str(q), str(aut), moeda(v), str(canc), str(rej), str(xml)])
    linhas.append(["Total", str(sum(len(r.notas) for r in resumos)), "", "", "", "", str(sum(r.xml_no_zip for r in resumos))])
    tab = Table(linhas, repeatRows=1, colWidths=[11 * cm, 2 * cm, 2.4 * cm, 3.4 * cm, 2.2 * cm, 2.2 * cm, 2.4 * cm])
    tab.setStyle(estilo)
    doc.build([Paragraph("Exportação de todas as empresas", est["Title"]),
               Paragraph(f"Gerado em {gerado_em.astimezone():%d/%m/%Y %H:%M:%S}", est["BodyText"]), Spacer(1, 6),
               filtros, Spacer(1, 10), tab])
    return buf.getvalue()


def gerar(db: Session, exp: Exportacao) -> None:
    f = Filtros.model_validate(exp.filtros)
    dados = config().dados_dir
    destino = dados / "exportacoes" / f"{exp.id}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    gerado_em = datetime.now(timezone.utc)
    resumos: list[Resumo] = []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        if f.escopo == "todas":
            for e in empresas_do_escopo(db, exp.empresa_id, f):
                if not selecionar_notas(db, e.id, f):
                    # empresa sem notas no filtro: sem pasta, mas listada no resumo
                    resumos.append(Resumo(empresa=e, filtros=f, gerado_em=gerado_em, notas=[], eventos=[], xml_no_zip=0))
                    continue
                resumos.append(_escrever_empresa(z, db, e, f, f"{pasta_empresa(e)}/", gerado_em))
            if f.relatorio == "xlsx":
                z.writestr("resumo_empresas.xlsx", resumo_empresas_xlsx(resumos, f, gerado_em))
            else:
                z.writestr("resumo_empresas.pdf", resumo_empresas_pdf(resumos, f, gerado_em))
        else:
            resumos.append(_escrever_empresa(z, db, db.get(Empresa, exp.empresa_id), f, "", gerado_em))
    os.replace(tmp, destino)
    ausentes = sum(len(r.ausentes) for r in resumos)
    exp.total_notas = sum(len(r.notas) for r in resumos)
    exp.zip_path = destino.relative_to(dados).as_posix()
    exp.status = "concluido"
    exp.erro = f"{ausentes} XML(s) não encontrado(s) no computador; listados no relatório." if ausentes else None


class Exportador:
    """Uma geração por vez, em segundo plano."""

    def __init__(self, sessao_factory: Callable[[], Session]):
        self._sf = sessao_factory
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="exportacao")
        self._lock = threading.Lock()

    def retomar_pendentes(self) -> None:
        with self._sf() as db:
            ids = [e.id for e in db.scalars(select(Exportacao).where(Exportacao.status.in_(["fila", "gerando"])))]
        for i in ids:
            self.enfileirar(i)

    def enfileirar(self, exp_id: int):
        return self._pool.submit(self._rodar, exp_id)

    def parar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _rodar(self, exp_id: int) -> None:
        with self._sf() as db:
            exp = db.get(Exportacao, exp_id)
            if exp is None or exp.status not in ("fila", "gerando"):
                return
            exp.status = "gerando"
            db.commit()
            barramento.publicar({"tipo": "exportacao", "id": exp.id, "status": exp.status})
            try:
                gerar(db, exp)
            except Exception as e:  # noqa: BLE001
                log.exception("Falha na exportação %s", exp_id)
                db.rollback()
                exp = db.get(Exportacao, exp_id)
                exp.status, exp.erro = "erro", f"{type(e).__name__}: {e}"
            db.commit()
            barramento.publicar({"tipo": "exportacao", "id": exp.id, "status": exp.status})
