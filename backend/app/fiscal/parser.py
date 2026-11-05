"""Leitura de XML de NFS-e e de evento (padrão nacional), com caminhos explícitos (lxml)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
N = {"n": NS}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)


class XmlInvalido(ValueError):
    pass


def _raiz(xml: bytes):
    try:
        return etree.fromstring(xml, _PARSER)
    except etree.XMLSyntaxError as e:
        raise XmlInvalido(f"XML malformado: {e}") from None


def _t(el, caminho: str) -> str | None:
    if el is None:
        return None
    r = el.find(caminho, N)
    if r is None or r.text is None:
        return None
    v = r.text.strip()
    return v or None


def _doc(el, grupo: str) -> str | None:
    """CNPJ ou CPF dentro de um grupo (prest, toma, interm, emit)."""
    g = el.find(grupo, N) if el is not None else None
    if g is None:
        return None
    return _t(g, "n:CNPJ") or _t(g, "n:CPF") or _t(g, "n:NIF")


def _dec(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _d(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


@dataclass
class DadosNfse:
    chave: str
    numero: str | None
    serie: str | None
    n_dps: str | None
    data_emissao: datetime | None
    competencia: date | None
    data_processamento: datetime | None
    emitente_doc: str | None
    emitente_nome: str | None
    emitente_uf: str | None
    prestador_doc: str | None
    tomador_doc: str | None
    tomador_nome: str | None
    intermediario_doc: str | None
    valor_servico: Decimal | None
    valor_liquido: Decimal | None
    valor_iss: Decimal | None
    municipio: str | None
    c_stat: str | None

    def papel(self, doc_empresa: str) -> str:
        if (self.prestador_doc or self.emitente_doc) == doc_empresa:
            return "prestada"
        if self.tomador_doc == doc_empresa:
            return "tomada"
        if self.intermediario_doc == doc_empresa:
            return "intermediada"
        return "outra"

    @property
    def mes_arquivo(self) -> str:
        ref = self.competencia or (self.data_emissao.date() if self.data_emissao else None) or \
            (self.data_processamento.date() if self.data_processamento else None)
        return ref.strftime("%Y-%m") if ref else "sem-data"


def parse_nfse(xml: bytes) -> DadosNfse:
    raiz = _raiz(xml)
    if etree.QName(raiz).localname != "NFSe":
        raise XmlInvalido(f"Raiz inesperada para NFS-e: {etree.QName(raiz).localname}")
    inf = raiz.find("n:infNFSe", N)
    if inf is None:
        raise XmlInvalido("NFS-e sem infNFSe.")
    chave = re.sub(r"^NFS", "", inf.get("Id") or "")
    if not re.fullmatch(r"\d{50}", chave):
        raise XmlInvalido("Chave de acesso ausente ou inválida em infNFSe/@Id.")
    dps = inf.find("n:DPS/n:infDPS", N)
    emit = inf.find("n:emit", N)
    toma = dps.find("n:toma", N) if dps is not None else None
    return DadosNfse(
        chave=chave,
        numero=_t(inf, "n:nNFSe"),
        serie=_t(dps, "n:serie"),
        n_dps=_t(dps, "n:nDPS"),
        data_emissao=_dt(_t(dps, "n:dhEmi")),
        competencia=_d(_t(dps, "n:dCompet")),
        data_processamento=_dt(_t(inf, "n:dhProc")),
        emitente_doc=_t(emit, "n:CNPJ") or _t(emit, "n:CPF"),
        emitente_nome=_t(emit, "n:xNome"),
        emitente_uf=_t(emit, "n:enderNac/n:UF"),
        prestador_doc=_doc(dps, "n:prest"),
        tomador_doc=_doc(dps, "n:toma"),
        tomador_nome=_t(toma, "n:xNome"),
        intermediario_doc=_doc(dps, "n:interm"),
        valor_servico=_dec(_t(dps, "n:valores/n:vServPrest/n:vServ")),
        valor_liquido=_dec(_t(inf, "n:valores/n:vLiq")),
        valor_iss=_dec(_t(inf, "n:valores/n:vISSQN")),
        municipio=_t(inf, "n:xLocPrestacao"),
        c_stat=_t(inf, "n:cStat"),
    )


@dataclass
class DadosEvento:
    chave: str
    codigo: str | None
    descricao: str | None
    data_evento: datetime | None
    n_seq: str | None

    @property
    def mes_arquivo(self) -> str:
        return self.data_evento.strftime("%Y-%m") if self.data_evento else "sem-data"


def parse_evento(xml: bytes) -> DadosEvento:
    raiz = _raiz(xml)
    if etree.QName(raiz).localname != "evento":
        raise XmlInvalido(f"Raiz inesperada para evento: {etree.QName(raiz).localname}")
    inf = raiz.find("n:infEvento", N)
    ped = inf.find("n:pedRegEvento/n:infPedReg", N) if inf is not None else None
    if ped is None:
        raise XmlInvalido("Evento sem infPedReg.")
    chave = _t(ped, "n:chNFSe")
    if not chave or not re.fullmatch(r"\d{50}", chave):
        raise XmlInvalido("Evento sem chave de acesso (chNFSe).")
    codigo = descricao = None
    for filho in ped:
        nome = etree.QName(filho).localname
        if re.fullmatch(r"e\d{6}", nome):
            codigo, descricao = nome[1:], _t(filho, "n:xDesc")
            break
    if codigo is None:  # reserva: fim do Id (EVT + chave(50) + código(6) + seq(3))
        m = re.fullmatch(r"EVT\d{50}(\d{6})\d{3}", inf.get("Id") or "")
        codigo = m.group(1) if m else None
    return DadosEvento(
        chave=chave, codigo=codigo, descricao=descricao,
        data_evento=_dt(_t(ped, "n:dhEvento")) or _dt(_t(inf, "n:dhProc")),
        n_seq=_t(inf, "n:nSeqEvento"),
    )
