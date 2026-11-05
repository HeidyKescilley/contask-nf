"""DANFSe v2.0 gerado localmente a partir do XML, conforme a NT SE/CGNFS-e nº 008/2026 (v1.02).

A API de geração do ADN foi suspensa em 03/08/2026; cada sistema gera o próprio DANFSe.
Regras seguidas:
- Campos representam as tags do XML; nada fora do XML é impresso (exceto a marca d'água
  CANCELADA/SUBSTITUÍDA exigida pelo item 2.5). Campos sem informação recebem "-" (nota 12).
- A4 retrato, página única, borda de 1 pt, linhas de 0,5 pt, cabeçalho/títulos com fundo cinza 5%.
- Fontes Arial (rótulos) e Microsoft Sans Serif (conteúdo), quando disponíveis no Windows.
- Posições e tamanhos do item 2.4.5 (cm); blocos não identificados viram uma linha de aviso (notas 2–4)
  e o espaço liberado vai para "Informações Complementares".
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from lxml import etree
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .parser import N, XmlInvalido

DADOS = Path(__file__).parent / "dados"
URL_QR = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave="
CINZA_5 = Color(0.95, 0.95, 0.95)
CINZA_K35 = Color(0.65, 0.65, 0.65)

# --- Tabelas do Anexo I (leiaute DPS/NFS-e) ---------------------------------------------
T_EMIT = {"1": "Prestador", "2": "Tomador", "3": "Intermediário"}
T_CSTAT = {"100": "NFS-e Gerada", "101": "NFS-e de Substituição Gerada", "102": "NFS-e de Decisão Judicial ou Administrativa",
           "103": "NFS-e Avulsa", "107": "NFS-e MEI"}
T_FIN = {"0": "NFS-e regular"}
T_AMBGER = {"1": "Sistema Próprio do Município", "2": "Sefin Nacional NFS-e"}
T_TPAMB = {"1": "Produção", "2": "Homologação"}
T_SIMPNAC = {"1": "Não Optante", "2": "Optante - Microempreendedor Individual (MEI)",
             "3": "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)"}
T_REGSN = {"1": "Regime de apuração dos tributos federais e municipal pelo SN",
           "2": "Regime de apuração dos tributos federais pelo SN e o ISSQN pela NFS-e conforme respectiva legislação municipal do tributo",
           "3": "Regime de apuração dos tributos federais e municipal pela NFS-e conforme respectivas legislações federal e municipal de cada tributo"}
T_TRIBISS = {"1": "Operação Tributável", "2": "Imunidade", "3": "Exportação de Serviço", "4": "Não Incidência"}
T_REGESP = {"0": "Nenhum", "1": "Ato Cooperado (Cooperativa)", "2": "Estimativa", "3": "Microempresa Municipal",
            "4": "Notário ou Registrador", "5": "Profissional Autônomo", "6": "Sociedade de Profissionais", "9": "Outros"}
T_IMUN = {"0": "Imunidade (tipo não informado na nota de origem)", "1": "Patrimônio, renda ou serviços, uns dos outros",
          "2": "Entidades religiosas e templos de qualquer culto", "3": "Partidos políticos, sindicatos, educação e assistência social",
          "4": "Livros, jornais, periódicos e o papel destinado a sua impressão", "5": "Fonogramas e videofonogramas musicais"}
T_SUSP = {"1": "Exigibilidade Suspensa por Decisão Judicial", "2": "Exigibilidade Suspensa por Processo Administrativo"}
T_RETISS = {"1": "Não Retido", "2": "Retido pelo Tomador", "3": "Retido pelo Intermediário"}
T_RETPC = {"0": "PIS/COFINS/CSLL Não Retidos", "1": "PIS/COFINS Retido", "2": "PIS/COFINS Não Retido",
           "3": "PIS/COFINS/CSLL Retidos", "4": "PIS/COFINS Retidos, CSLL Não Retido", "5": "PIS Retido, COFINS/CSLL Não Retido",
           "6": "COFINS Retido, PIS/CSLL Não Retido", "7": "PIS Não Retido, COFINS/CSLL Retidos",
           "8": "PIS/COFINS Não Retidos, CSLL Retido", "9": "COFINS Não Retido, PIS/CSLL Retidos"}
T_BM = {"1": "Isenção", "2": "Redução da BC em %", "3": "Redução da BC em R$", "4": "Alíquota Diferenciada"}


@lru_cache
def _ibge() -> dict:
    return json.loads((DADOS / "ibge.json").read_text(encoding="utf-8"))


def municipio_uf(codigo: str | None) -> str | None:
    if not codigo:
        return None
    m = _ibge()["municipios"].get(codigo)
    return f"{m[0]} / {m[1]}" if m else None


@lru_cache
def _fontes() -> tuple[str, str, str]:
    """(rótulo, rótulo negrito, conteúdo). Arial e Microsoft Sans Serif quando existirem."""
    pasta = Path(r"C:\Windows\Fonts")
    try:
        pdfmetrics.registerFont(TTFont("Arial", str(pasta / "arial.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-Bold", str(pasta / "arialbd.ttf")))
        rot, rotb = "Arial", "Arial-Bold"
    except Exception:  # noqa: BLE001
        rot, rotb = "Helvetica", "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont("MSSansSerif", str(pasta / "micross.ttf")))
        cont = "MSSansSerif"
    except Exception:  # noqa: BLE001
        cont = rot
    return rot, rotb, cont


# --- Formatação ---------------------------------------------------------------------------

def _dec(v: str | None) -> Decimal | None:
    try:
        return Decimal(v) if v not in (None, "") else None
    except InvalidOperation:
        return None


def moeda(v) -> str:
    d = v if isinstance(v, Decimal) else _dec(v)
    if d is None:
        return "-"
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def pct(v: str | None) -> str:
    d = _dec(v)
    return "-" if d is None else f"{d:.2f}".replace(".", ",") + "%"


def doc(v: str | None) -> str:
    if not v:
        return "-"
    c = re.sub(r"[^0-9A-Za-z]", "", v)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    if len(c) == 11 and c.isdigit():
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return v


def data(v: str | None) -> str:
    if not v:
        return "-"
    try:
        return date.fromisoformat(v[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return v


def data_hora(v: str | None) -> str:
    if not v:
        return "-"
    try:
        return datetime.fromisoformat(v).strftime("%d/%m/%Y %H:%M:%S")  # mantém o fuso do XML
    except ValueError:
        return v


def cep(v: str | None) -> str | None:
    if not v:
        return None
    c = re.sub(r"\D", "", v)
    return f"{c[:2]}.{c[2:5]}-{c[5:]}" if len(c) == 8 else v


def cod_trib_nac(v: str | None) -> str | None:
    if not v:
        return None
    return f"{v[:2]}.{v[2:4]}.{v[4:6]}" if re.fullmatch(r"\d{6}", v) else v


def nbs(v: str | None) -> str | None:
    if not v:
        return None
    return f"{v[0]}.{v[1:5]}.{v[5:7]}.{v[7:9]}" if re.fullmatch(r"\d{9}", v) else v


def junta(*partes: str | None, sep: str = " / ") -> str:
    p = [x for x in partes if x]
    return sep.join(p) if p else "-"


# --- Leitura do XML ---------------------------------------------------------------------------

class X:
    """Atalhos de leitura com o namespace da NFS-e."""

    def __init__(self, el):
        self.el = el

    def t(self, caminho: str) -> str | None:
        if self.el is None:
            return None
        r = self.el.find("/".join(f"n:{p}" for p in caminho.split("/")), N)
        if r is None or r.text is None:
            return None
        return r.text.strip() or None

    def g(self, caminho: str) -> "X":
        if self.el is None:
            return X(None)
        return X(self.el.find("/".join(f"n:{p}" for p in caminho.split("/")), N))

    def __bool__(self):
        return self.el is not None


@dataclass
class Pessoa:
    doc: str
    im: str
    fone: str
    nome: str
    municipio: str
    ibge_cep: str
    endereco: str
    email: str


def pessoa(p: X) -> Pessoa | None:
    if not p:
        return None
    end = p.g("end")
    nac, ext = end.g("endNac"), end.g("endExt")
    cmun = nac.t("cMun")
    municipio = municipio_uf(cmun) if cmun else ext.t("xCidade")
    ibge_cep = junta(cmun, cep(nac.t("CEP"))) if nac else junta(ext.t("cEndPost"))
    endereco = ", ".join(x for x in (end.t("xLgr"), end.t("nro"), end.t("xCpl"), end.t("xBairro")) if x) or "-"
    return Pessoa(doc=doc(p.t("CNPJ") or p.t("CPF") or p.t("NIF")), im=p.t("IM") or "-", fone=p.t("fone") or "-",
                  nome=p.t("xNome") or "-", municipio=municipio or "-", ibge_cep=ibge_cep, endereco=endereco,
                  email=p.t("email") or "-")


# --- Desenho ------------------------------------------------------------------------------------

class Desenho:
    def __init__(self, c: Canvas):
        self.c = c
        self.rot, self.rotb, self.cont = _fontes()
        self.alt_pagina = A4[1]

    def _y(self, topo_cm: float, alt_cm: float) -> float:
        return self.alt_pagina - (topo_cm + alt_cm) * cm

    def caixa(self, x, y, w, h, fundo=False):
        self.c.setLineWidth(0.5)
        if fundo:
            self.c.setFillColor(CINZA_5)
            self.c.rect(x * cm, self._y(y, h), w * cm, h * cm, stroke=1, fill=1)
            self.c.setFillColor(black)
        else:
            self.c.rect(x * cm, self._y(y, h), w * cm, h * cm, stroke=1, fill=0)

    def cabe(self, texto: str, fonte: str, tam: float, largura_cm: float) -> str:
        """Corta com reticências para caber na largura."""
        larg = largura_cm * cm
        if pdfmetrics.stringWidth(texto, fonte, tam) <= larg:
            return texto
        while texto and pdfmetrics.stringWidth(texto + "...", fonte, tam) > larg:
            texto = texto[:-1]
        return texto.rstrip() + "..."

    def linhas(self, texto: str, fonte: str, tam: float, largura_cm: float, max_linhas: int) -> list[str]:
        larg, saida = largura_cm * cm, []
        for paragrafo in (texto or "").replace("\r", "").split("\n"):
            palavras, atual = paragrafo.split(" "), ""
            for p in palavras:
                teste = f"{atual} {p}".strip()
                if pdfmetrics.stringWidth(teste, fonte, tam) <= larg:
                    atual = teste
                else:
                    if atual:
                        saida.append(atual)
                    while pdfmetrics.stringWidth(p, fonte, tam) > larg:  # palavra maior que a linha
                        corte = len(p)
                        while corte > 1 and pdfmetrics.stringWidth(p[:corte], fonte, tam) > larg:
                            corte -= 1
                        saida.append(p[:corte])
                        p = p[corte:]
                    atual = p
            saida.append(atual)
        if len(saida) > max_linhas:
            saida = saida[:max_linhas]
            saida[-1] = self.cabe(saida[-1] + " …", fonte, tam, largura_cm).replace(" …", "...")
        return saida

    def campo(self, x, y, w, h, rotulo: str | None, valor: str | None, *, fundo=False, rotulo_tam=6,
              caixa_alta=False, valor_tam=7, multilinha=False):
        self.caixa(x, y, w, h, fundo)
        pad = 0.08
        topo = self.alt_pagina - y * cm
        cursor = topo - (rotulo_tam + 1)
        if rotulo:
            self.c.setFont(self.rotb, rotulo_tam)
            self.c.drawString((x + pad) * cm, cursor, rotulo.upper() if caixa_alta else rotulo)
            cursor -= valor_tam + 2
        else:
            cursor = topo - (valor_tam + 2)
        self.c.setFont(self.cont, valor_tam)
        texto = valor if valor not in (None, "") else "-"
        if multilinha:
            max_l = max(1, int(((cursor - (topo - h * cm)) / (valor_tam + 1.5))) + 1)
            for linha in self.linhas(texto, self.cont, valor_tam, w - 2 * pad, max_l):
                self.c.drawString((x + pad) * cm, cursor, linha)
                cursor -= valor_tam + 1.5
        else:
            self.c.drawString((x + pad) * cm, cursor, self.cabe(texto, self.cont, valor_tam, w - 2 * pad))

    def titulo(self, x, y, w, h, texto):
        self.caixa(x, y, w, h, fundo=True)
        self.c.setFont(self.rotb, 7)
        linhas = self.linhas(texto.upper(), self.rotb, 7, w - 0.16, 2)
        topo = self.alt_pagina - y * cm
        base = topo - (h * cm - len(linhas) * 8) / 2 - 7
        for i, l in enumerate(linhas):
            self.c.drawString((x + 0.08) * cm, base - i * 8, l)

    def aviso(self, y, texto, h=0.32):
        self.caixa(0.30, y, 20.40, h, fundo=True)
        self.c.setFont(self.rotb, 7)
        self.c.drawCentredString(10.50 * cm, self._y(y, h) + (h * cm - 7) / 2 + 1, texto)


# --- Gerador ---------------------------------------------------------------------------------------

COLS = (0.30, 5.41, 10.51, 15.62)
L1, L2 = 5.09, 10.19  # larguras de 1 e 2 colunas
H = 0.63


def gerar_danfse(xml: bytes, *, marca_dagua: str | None = None) -> bytes:
    """Gera o PDF. `marca_dagua`: "CANCELADA" ou "SUBSTITUÍDA" (item 2.5)."""
    try:
        raiz = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        raise XmlInvalido(str(e)) from None
    inf = X(raiz.find("n:infNFSe", N))
    if not inf:
        raise XmlInvalido("XML não é uma NFS-e (sem infNFSe).")
    dps = inf.g("DPS/infDPS")
    chave = re.sub(r"^NFS", "", inf.el.get("Id") or "")
    ibscbs_dps, ibscbs = dps.g("IBSCBS"), inf.g("IBSCBS")

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(f"DANFSe {chave}")
    c.setAuthor("Gerado a partir do XML da NFS-e (NT SE/CGNFS-e 008/2026)")
    d = Desenho(c)

    # Borda da página (1 pt)
    c.setLineWidth(1)
    c.rect(0.30 * cm, d._y(0.30, 29.10), 20.40 * cm, 29.10 * cm)

    # ---- Cabeçalho -------------------------------------------------------------------------------
    d.caixa(0.30, 0.30, 20.40, 1.16, fundo=True)
    logo = DADOS / "logo_nfse_horizontal.png"
    if logo.is_file():
        c.drawImage(str(logo), 0.49 * cm, d._y(0.44, 0.85), width=4.00 * cm, height=0.85 * cm,
                    preserveAspectRatio=True, anchor="w", mask="auto")
    c.setFont(d.rotb, 9)
    homolog = dps.t("tpAmb") == "2"
    yc = d.alt_pagina - 0.30 * cm - (0.62 if homolog else 0.48) * cm
    c.drawCentredString(10.50 * cm, yc, "DANFSe v2.0")
    c.drawCentredString(10.50 * cm, yc - 11, "Documento Auxiliar da NFS-e")
    if homolog:
        c.setFillColor(Color(1, 0, 0))
        c.drawCentredString(10.50 * cm, yc - 22, "NFS-e SEM VALIDADE JURÍDICA")
        c.setFillColor(black)
    c_trib = dps.t("serv/cServ/cTribNac") or ""
    c.setFont(d.cont, 8)
    if not c_trib.startswith("99"):
        uf_emit = inf.t("emit/enderNac/UF")
        c.drawString(15.70 * cm, d._y(0.30, 0.42), d.cabe(f"Município: {junta(inf.t('xLocEmi'), uf_emit)}", d.cont, 8, 4.9))
    c.setFont(d.cont, 6)
    c.drawString(15.70 * cm, d._y(0.97, 0.20), d.cabe(f"Ambiente gerador: {T_AMBGER.get(inf.t('ambGer') or '', inf.t('ambGer') or '-')}", d.cont, 6, 4.9))
    c.drawString(15.70 * cm, d._y(1.22, 0.20), f"Ambiente: {T_TPAMB.get(dps.t('tpAmb') or '', dps.t('tpAmb') or '-')}")

    # ---- Dados da NFS-e ----------------------------------------------------------------------------
    d.caixa(0.30, 1.48, 20.40, 2.84)
    d.campo(0.30, 1.48, 15.30, 0.77, "CHAVE DE ACESSO DA NFS-E", chave, rotulo_tam=7, valor_tam=9)
    linha = [
        [("NÚMERO DA NFS-E", inf.t("nNFSe")), ("COMPETÊNCIA DA NFS-E", data(dps.t("dCompet"))),
         ("DATA E HORA DA EMISSÃO DA NFS-E", data_hora(inf.t("dhProc")))],
        [("NÚMERO DA DPS", dps.t("nDPS")), ("SÉRIE DA DPS", dps.t("serie")),
         ("DATA E HORA DA EMISSÃO DA DPS", data_hora(dps.t("dhEmi")))],
        [("EMITENTE DA NFS-E", T_EMIT.get(dps.t("tpEmit") or "", dps.t("tpEmit"))),
         ("SITUAÇÃO DA NFS-E", T_CSTAT.get(inf.t("cStat") or "", inf.t("cStat"))),
         ("FINALIDADE", T_FIN.get(ibscbs_dps.t("finNFSe") or "", ibscbs_dps.t("finNFSe")))],
    ]
    for i, campos in enumerate(linha):
        y = 2.27 + i * 0.69
        for j, (rot, val) in enumerate(campos):
            d.campo(COLS[j], y, L1, 0.67, rot, val, rotulo_tam=7, fundo=(rot == "EMITENTE DA NFS-E"))
    qr = QrCodeWidget(URL_QR + chave)
    b = qr.getBounds()
    tam = 1.52 * cm
    dr = Drawing(tam, tam, transform=[tam / (b[2] - b[0]), 0, 0, tam / (b[3] - b[1]), 0, 0])
    dr.add(qr)
    renderPDF.draw(dr, c, 17.48 * cm, d._y(1.67, 1.52))
    c.setFont(d.cont, 6)
    for i, t in enumerate(["A autenticidade desta NFS-e pode ser verificada", "pela leitura deste código QR ou pela consulta da",
                           "chave de acesso no portal nacional da NFS-e"]):
        c.drawCentredString(18.16 * cm, d._y(3.36 + i * 0.22, 0.20), t)

    y = 4.34

    def bloco_pessoa(titulo: str, p: Pessoa | None, *, com_im=True, rodape: tuple | None = None, vazio: str):
        nonlocal y
        if p is None:
            d.aviso(y, vazio)
            y += 0.32
            return
        d.titulo(COLS[0], y, L1, H, titulo)
        d.campo(COLS[1], y, L1, H, "CNPJ / CPF / NIF", p.doc)
        if com_im:
            d.campo(COLS[2], y, L1, H, "Indicador Municipal (Inscrição)", p.im)
        else:
            d.caixa(COLS[2], y, L1, H)
        d.campo(COLS[3], y, L1, H, "Telefone", p.fone)
        y += H
        d.campo(COLS[0], y, L2, H, "Nome / Nome Empresarial", p.nome)
        d.campo(COLS[2], y, L1, H, "Município / Sigla UF", p.municipio)
        d.campo(COLS[3], y, L1, H, "Código IBGE / CEP", p.ibge_cep)
        y += H
        d.campo(COLS[0], y, L2, H, "Endereço", p.endereco)
        d.campo(COLS[2], y, L2, H, "E-mail", p.email)
        y += H
        if rodape:
            (r1, v1), (r2, v2) = rodape
            d.campo(COLS[0], y, L1, H, r1, v1)
            d.caixa(COLS[1], y, L1, H)
            d.campo(COLS[2], y, L2, H, r2, v2)
            y += H

    prest = dps.g("prest")
    reg = prest.g("regTrib")
    p_prest = pessoa(prest)
    emit = inf.g("emit")
    if emit and (p_prest is None or dps.t("tpEmit") in (None, "1")):
        # O prestador é o emitente: o grupo emit (do mesmo XML) completa o que a DPS não trouxe
        en = emit.g("enderNac")
        p_emit = Pessoa(
            doc=doc(emit.t("CNPJ") or emit.t("CPF")), im=emit.t("IM") or "-", fone=emit.t("fone") or "-",
            nome=emit.t("xNome") or "-", municipio=municipio_uf(en.t("cMun")) or "-",
            ibge_cep=junta(en.t("cMun"), cep(en.t("CEP"))),
            endereco=", ".join(x for x in (en.t("xLgr"), en.t("nro"), en.t("xCpl"), en.t("xBairro")) if x) or "-",
            email=emit.t("email") or "-")
        if p_prest is None:
            p_prest = p_emit
        else:
            for campo in ("im", "fone", "nome", "municipio", "ibge_cep", "endereco", "email"):
                if getattr(p_prest, campo) in ("-", "") and getattr(p_emit, campo) not in ("-", ""):
                    setattr(p_prest, campo, getattr(p_emit, campo))
    bloco_pessoa("Prestador / Fornecedor", p_prest,
                 rodape=(("Simples Nacional na Data de Competência", T_SIMPNAC.get(reg.t("opSimpNac") or "", reg.t("opSimpNac"))),
                         ("Regime de Apuração Tributária pelo SN", T_REGSN.get(reg.t("regApTribSN") or "", reg.t("regApTribSN")))),
                 vazio="PRESTADOR NÃO IDENTIFICADO NA NFS-e")
    toma = pessoa(dps.g("toma"))
    bloco_pessoa("Tomador / Adquirente", toma, vazio="TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    dest = pessoa(ibscbs_dps.g("dest"))
    if dest is None and toma is not None:
        d.aviso(y, "O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO")
        y += 0.32
    else:
        bloco_pessoa("Destinatário da Operação", dest, com_im=False, vazio="DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    bloco_pessoa("Intermediário da Operação", pessoa(dps.g("interm")), vazio="INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")

    # ---- Serviço prestado ----------------------------------------------------------------------------
    serv = dps.g("serv")
    d.titulo(COLS[0], y, L1, H, "Serviço Prestado")
    d.campo(COLS[1], y, L1, H, "Código de Tributação Nacional / Municipal", junta(cod_trib_nac(serv.t("cServ/cTribNac")), serv.t("cServ/cTribMun")))
    d.campo(COLS[2], y, L1, H, "Código da NBS", nbs(serv.t("cServ/cNBS")))
    pais_prest = serv.t("locPrest/cPaisPrestacao") or "BR"
    uf_prest = (_ibge()["municipios"].get(serv.t("locPrest/cLocPrestacao") or "") or [None, None])[1]
    d.campo(COLS[3], y, L1, H, "Local da Prestação / Sigla UF / País", junta(inf.t("xLocPrestacao"), uf_prest, pais_prest))
    y += H
    desc_trib = inf.t("xTribMun") or inf.t("xTribNac")
    d.campo(COLS[0], y, 20.40, 0.38, None, desc_trib)
    y += 0.38
    desc_serv = serv.t("cServ/xDescServ") or "-"
    n_lin = len(d.linhas(desc_serv, d.cont, 7, 20.24, 14))
    h_desc = max(0.63, 0.32 + n_lin * 0.30)
    d.campo(COLS[0], y, 20.40, h_desc, "Descrição do Serviço", desc_serv, multilinha=True)
    y += h_desc

    # ---- Tributação municipal ------------------------------------------------------------------------
    trib = dps.g("valores/trib")
    mun = trib.g("tribMun")
    vals = inf.g("valores")
    if not mun:
        d.aviso(y, "TRIBUTAÇÃO MUNICIPAL (ISSQN) - OPERAÇÃO NÃO SUJEITA AO ISSQN")
        y += 0.32
    else:
        d.titulo(COLS[0], y, L1, H, "Tributação Municipal (ISSQN)")
        d.campo(COLS[1], y, L1, H, "Tipo de Tributação do ISSQN", T_TRIBISS.get(mun.t("tribISSQN") or "", mun.t("tribISSQN")))
        uf_inc = (_ibge()["municipios"].get(inf.t("cLocIncid") or "") or [None, None])[1]
        d.campo(COLS[2], y, L2, H, "Município / Sigla UF / País da Incidência do ISSQN",
                junta(inf.t("xLocIncid"), uf_inc, mun.t("cPaisResult") or ("BR" if inf.t("xLocIncid") else None)))
        y += H
        reg_esp, imun = reg.t("regEspTrib"), mun.t("tpImunidade")
        susp, nproc = mun.t("exigSusp/tpSusp"), mun.t("exigSusp/nProcesso")
        if any((reg_esp, imun, susp, nproc)):  # nota 5
            d.campo(COLS[0], y, L1, H, "Regime Especial de Tributação do ISSQN", T_REGESP.get(reg_esp or "", reg_esp))
            d.campo(COLS[1], y, L1, H, "Tipo de Imunidade do ISSQN", T_IMUN.get(imun or "", imun))
            d.campo(COLS[2], y, L1, H, "Suspensão da Exigibilidade do ISSQN", T_SUSP.get(susp or "", susp))
            d.campo(COLS[3], y, L1, H, "Número Processo Suspensão", nproc)
            y += H
        tp_bm = vals.t("tpBM")
        calc_bm = vals.t("vCalcBM") or mun.t("BM/vRedBCBM")
        ded = dps.t("valores/vDedRed/vDR") or vals.t("vCalcDR")
        desc_inc = dps.t("valores/vDescCondIncond/vDescIncond")
        if any((tp_bm, calc_bm, ded, desc_inc)):  # nota 5
            d.campo(COLS[0], y, L1, H, "Benefício Municipal", T_BM.get(tp_bm or "", tp_bm))
            d.campo(COLS[1], y, L1, H, "Cálculo do BM", moeda(calc_bm) if calc_bm else None)
            d.campo(COLS[2], y, L1, H, "Total Deduções/Reduções", moeda(ded) if ded else None)
            d.campo(COLS[3], y, L1, H, "Desconto Incondicionado", moeda(desc_inc) if desc_inc else None)
            y += H
        d.campo(COLS[0], y, L1, H, "BC ISSQN", moeda(vals.t("vBC")))
        d.campo(COLS[1], y, L1, H, "Alíquota Aplicada", pct(vals.t("pAliqAplic")))
        d.campo(COLS[2], y, L1, H, "Retenção do ISSQN", T_RETISS.get(mun.t("tpRetISSQN") or "", mun.t("tpRetISSQN")))
        d.campo(COLS[3], y, L1, H, "ISSQN Apurado", moeda(vals.t("vISSQN")))
        y += H

    # ---- Tributação federal ----------------------------------------------------------------------------
    fed = trib.g("tribFed")
    pc = fed.g("piscofins")
    tp_ret_pc = pc.t("tpRetPisCofins")
    retido = tp_ret_pc == "1"
    csll = _dec(fed.t("vRetCSLL"))
    if retido:
        soma = sum((x for x in (csll, _dec(pc.t("vPis")), _dec(pc.t("vCofins"))) if x is not None), Decimal(0))
        contrib = moeda(soma)
    else:
        contrib = moeda(csll)
    d.titulo(COLS[0], y, L1, H, "Tributação Federal (Exceto CBS)")
    d.campo(COLS[1], y, L1, H, "IRRF", moeda(fed.t("vRetIRRF")))
    d.campo(COLS[2], y, L1, H, "Contribuição Previdenciária - Retida", moeda(fed.t("vRetCP")))
    d.campo(COLS[3], y, L1, H, "Contribuições Sociais - Retidas", contrib)
    y += H
    compet = dps.t("dCompet") or ""
    if compet[:4] and compet[:4] <= "2026":  # nota 6
        d.campo(COLS[0], y, L1, H, "PIS - Débito Apuração Própria", "R$ 0,00" if retido else moeda(pc.t("vPis")))
        d.campo(COLS[1], y, L1, H, "COFINS - Débito Apuração Própria", "R$ 0,00" if retido else moeda(pc.t("vCofins")))
        d.campo(COLS[2], y, L2, H, "Descrição Contrib. Sociais - Retidas", T_RETPC.get(tp_ret_pc or "", tp_ret_pc))
        y += H

    # ---- Tributação IBS/CBS --------------------------------------------------------------------------------
    gtrib = ibscbs_dps.g("valores/trib/gIBSCBS")
    iv = ibscbs.g("valores")
    tot = ibscbs.g("totCIBS")
    d.titulo(COLS[0], y, L1, H, "Tributação IBS / CBS")
    d.campo(COLS[1], y, L1, H, "CST / cClassTrib", junta(gtrib.t("CST"), gtrib.t("cClassTrib")))
    loc_inc = ibscbs.t("cLocalidadeIncid")
    d.campo(COLS[2], y, L2, H, "Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF",
            junta(ibscbs_dps.t("cIndOp"), loc_inc, ibscbs.t("xLocalidadeIncid"),
                  (_ibge()["municipios"].get(loc_inc or "") or [None, None])[1]))
    y += H
    excl = [x for x in (_dec(dps.t("valores/vDescCondIncond/vDescIncond")), _dec(iv.t("vCalcReeRepRes")),
                        _dec(vals.t("vISSQN")), _dec(pc.t("vPis")), _dec(pc.t("vCofins"))) if x is not None]
    tem_ibs = bool(ibscbs)
    d.campo(COLS[0], y, L1, H, "Exclusões e Reduções da Base de Cálculo", moeda(sum(excl, Decimal(0))) if tem_ibs and excl else None)
    d.campo(COLS[1], y, L1, H, "Base de Cálculo Após Exclusões e Reduções", moeda(iv.t("vBC")) if iv.t("vBC") else None)
    reds = [iv.t("uf/pRedAliqUF"), iv.t("mun/pRedAliqMun"), iv.t("fed/pRedAliqCBS")]
    d.campo(COLS[2], y, L1, H, "Red. Alíquota IBS / Red. Alíquota CBS", " / ".join(pct(r) for r in reds) if any(reds) else None)
    aliqs = [iv.t("uf/pIBSUF"), iv.t("mun/pIBSMun")]
    d.campo(COLS[3], y, L1, H, "Alíquota - IBS UF / IBS Mun", " / ".join(pct(a) for a in aliqs) if any(aliqs) else None)
    y += H
    d.campo(COLS[0], y, L1, H, "Alíq. Efetiva Municipal - IBS", pct(iv.t("mun/pAliqEfetMun")) if iv.t("mun/pAliqEfetMun") else None)
    d.campo(COLS[1], y, L1, H, "Valor Apurado Municipal - IBS", moeda(tot.t("gIBS/gIBSMunTot/vIBSMun")) if tot.t("gIBS/gIBSMunTot/vIBSMun") else None)
    d.campo(COLS[2], y, L1, H, "Alíq. Efetiva Estadual - IBS", pct(iv.t("uf/pAliqEfetUF")) if iv.t("uf/pAliqEfetUF") else None)
    d.campo(COLS[3], y, L1, H, "Valor Apurado Estadual - IBS", moeda(tot.t("gIBS/gIBSUFTot/vIBSUF")) if tot.t("gIBS/gIBSUFTot/vIBSUF") else None)
    y += H
    d.campo(COLS[0], y, L1, H, "Valor Total Apurado - IBS", moeda(tot.t("gIBS/vIBSTot")) if tot.t("gIBS/vIBSTot") else None)
    d.campo(COLS[1], y, L1, H, "Alíquota - CBS", pct(iv.t("fed/pCBS")) if iv.t("fed/pCBS") else None)
    d.campo(COLS[2], y, L1, H, "Alíquota Efetiva - CBS", pct(iv.t("fed/pAliqEfetCBS")) if iv.t("fed/pAliqEfetCBS") else None)
    d.campo(COLS[3], y, L1, H, "Valor Total Apurado - CBS", moeda(tot.t("gCBS/vCBS")) if tot.t("gCBS/vCBS") else None)
    y += H

    # ---- Valor total -----------------------------------------------------------------------------------------
    HV = 0.67
    d.titulo(COLS[0], y, L1, HV, "Valor Total da NFS-e")
    d.campo(COLS[1], y, L1, HV, "Valor da Operação / Serviço", moeda(dps.t("valores/vServPrest/vServ")))
    d.campo(COLS[2], y, L1, HV, "Desconto Incondicionado", moeda(dps.t("valores/vDescCondIncond/vDescIncond")) if dps.t("valores/vDescCondIncond/vDescIncond") else None)
    d.campo(COLS[3], y, L1, HV, "Desconto Condicionado", moeda(dps.t("valores/vDescCondIncond/vDescCond")) if dps.t("valores/vDescCondIncond/vDescCond") else None)
    y += HV
    v_ibs, v_cbs = _dec(tot.t("gIBS/vIBSTot")), _dec(tot.t("gCBS/vCBS"))
    d.campo(COLS[0], y, L1, HV, "Total das Retenções (ISSQN / Federais)", moeda(vals.t("vTotalRet")) if vals.t("vTotalRet") else None)
    d.campo(COLS[1], y, L1, HV, "Valor Líquido da NFS-e", moeda(vals.t("vLiq")))
    d.campo(COLS[2], y, L1, HV, "Total do IBS/CBS", moeda((v_ibs or 0) + (v_cbs or 0)) if (v_ibs is not None or v_cbs is not None) else None)
    d.campo(COLS[3], y, L1, HV, "Valor Líquido da NFS-e + IBS/CBS", moeda(tot.t("vTotNF")) if tot.t("vTotNF") else None, fundo=True)
    y += HV

    # ---- Informações complementares (ocupa o restante da página) ---------------------------------------------------
    info = []
    comp = serv.g("infoCompl")
    for rot, val in (("Inf. Cont.", comp.t("xInfComp")), ("NFS-e Subst.", dps.t("subst/chSubstda")),
                     ("Doc. Ref.", comp.t("docRef")), ("Cod. Obra", serv.t("obra/cObra")),
                     ("Insc. Imob.", ibscbs_dps.t("imovel/inscImobFisc") or serv.t("obra/inscImobFisc")),
                     ("Cod. Evt.", serv.t("atvEvento/idAtvEvt")), ("Doc. Tec.", comp.t("idDocTec")),
                     ("Núm. Ped.", comp.t("xPed")), ("Item Ped.", comp.t("gItemPed/xItemPed")),
                     ("Inf. A. T. Mun.", inf.t("xOutInf") or vals.t("xOutInf"))):
        if val:
            info.append(f"{rot}: {val}")
    tt = trib.g("totTrib")
    if tt.t("vTotTrib/vTotTribFed") or tt.t("vTotTrib/vTotTribEst") or tt.t("vTotTrib/vTotTribMun"):
        totais = f"Federais: {moeda(tt.t('vTotTrib/vTotTribFed'))}; Estaduais: {moeda(tt.t('vTotTrib/vTotTribEst'))}; Municipais: {moeda(tt.t('vTotTrib/vTotTribMun'))}"
    elif tt.t("pTotTrib/pTotTribFed") or tt.t("pTotTrib/pTotTribEst") or tt.t("pTotTrib/pTotTribMun"):
        totais = f"Federais: {pct(tt.t('pTotTrib/pTotTribFed'))}; Estaduais: {pct(tt.t('pTotTrib/pTotTribEst'))}; Municipais: {pct(tt.t('pTotTrib/pTotTribMun'))}"
    else:
        totais = "Federais: -; Estaduais: -; Municipais: -"
    texto_info = " | ".join(info)
    if len(texto_info) > 1997:
        texto_info = texto_info[:1997] + "..."
    linha_totais = f"Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012: {totais}"
    d.titulo(COLS[0], y, 20.40, 0.39, "Informações Complementares")
    y += 0.39
    h_info = max(0.39, 29.40 - y)
    d.caixa(COLS[0], y, 20.40, h_info)
    c.setFont(d.cont, 7)
    cursor = d.alt_pagina - y * cm - 9
    max_l = max(1, int((h_info * cm - 12) / 8.5) - 1)
    for l in d.linhas(texto_info, d.cont, 7, 20.24, max_l) if texto_info else []:
        c.drawString(0.38 * cm, cursor, l)
        cursor -= 8.5
    c.drawString(0.38 * cm, cursor, d.cabe(linha_totais, d.cont, 7, 20.24))

    # ---- Marca d'água (item 2.5) ----------------------------------------------------------------------------------
    if marca_dagua:
        c.saveState()
        c.setFillColor(CINZA_K35)
        c.setFillAlpha(0.55)  # sobre o conteúdo, sem esconder os dados
        c.setFont(d.rot, 80)
        c.translate(10.5 * cm, 14.85 * cm)
        c.rotate(45)
        c.drawCentredString(0, -25, marca_dagua)
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()
