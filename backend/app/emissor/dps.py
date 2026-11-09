"""Montagem e validação da DPS e do pedido de cancelamento.

Há dois leiautes ativos ao mesmo tempo:
- produção (XSD v1.01 de 09/02/2026): cServ = cTribNac, cTribMun, xDescServ, cNBS; sem finNFSe;
- produção restrita (XSD de 20/10/2026, reforma tributária): finNFSe depois de tpEmit; cServ = cTribNac,
  cTribMun, cNBS, cIntContrib, xDescServ.
Regras de negócio aplicadas aqui estão anotadas com o código de rejeição da Sefin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
XSD = Path(__file__).with_name("xsd")
BRASILIA = timezone(timedelta(hours=-3))
VERSAO_APLICATIVO = "ContaskNF-1.0"

PRODUCAO, RESTRITA = 1, 2


class DpsInvalida(ValueError):
    """Mensagem pensada para ser mostrada ao usuário."""


def centavos(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _dec(v: Decimal) -> str:
    return f"{v:.2f}"


@dataclass
class Prestador:
    cnpj: str
    cod_municipio: str            # IBGE do município emissor (cLocEmi)
    op_simples: str               # 1 não optante | 2 MEI | 3 ME/EPP
    reg_ap_trib_sn: str | None
    reg_esp_trib: str
    inscricao_municipal: str | None = None


@dataclass
class TomadorDps:
    documento: str
    nome: str
    inscricao_municipal: str | None = None
    cep: str | None = None
    cod_municipio: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    telefone: str | None = None
    email: str | None = None

    @property
    def tem_endereco(self) -> bool:
        return all([self.cep, self.cod_municipio, self.logradouro, self.numero, self.bairro])


@dataclass
class Retencoes:
    iss: bool = False
    pis: Decimal = Decimal("0")
    cofins: Decimal = Decimal("0")
    csll: Decimal = Decimal("0")
    irrf: Decimal = Decimal("0")
    cp: Decimal = Decimal("0")   # INSS

    @property
    def tp_ret_pis_cofins(self) -> str:
        """Código tpRetPisCofins a partir de quais contribuições foram retidas."""
        chave = (self.pis > 0, self.cofins > 0, self.csll > 0)
        return {(False, False, False): "0", (True, True, True): "3", (True, True, False): "4",
                (True, False, False): "5", (False, True, False): "6", (False, True, True): "7",
                (False, False, True): "8", (True, False, True): "9"}[chave]

    @property
    def contribuicoes(self) -> Decimal:
        """vRetCSLL soma PIS, COFINS e CSLL retidos (observação do leiaute)."""
        return self.pis + self.cofins + self.csll

    @property
    def federais(self) -> Decimal:
        return self.contribuicoes + self.irrf + self.cp


@dataclass
class DadosDps:
    ambiente: int
    serie: str
    numero: int
    competencia: date
    prestador: Prestador
    tomador: TomadorDps | None
    ctribnac: str
    cnbs: str
    descricao: str
    valor: Decimal
    cod_municipio_prestacao: str
    ctribmun: str | None = None
    desconto_incondicionado: Decimal = Decimal("0")
    aliquota_iss: Decimal | None = None       # só quando a regra exige (ver precisa_aliquota)
    retencoes: Retencoes = field(default_factory=Retencoes)
    percentual_tributos_sn: Decimal | None = None
    info_complementar: str | None = None
    emitido_em: datetime | None = None

    @property
    def id_dps(self) -> str:
        return id_dps(self.prestador.cod_municipio, self.prestador.cnpj, self.serie, self.numero)


def id_dps(cod_municipio: str, cnpj: str, serie: str, numero: int) -> str:
    """DPS + IBGE(7) + tipo de inscrição (2 = CNPJ) + CNPJ(14) + série(5) + número(15)."""
    return f"DPS{cod_municipio}2{cnpj}{int(serie):05d}{int(numero):015d}"


def precisa_aliquota(p: Prestador, iss_retido: bool) -> bool:
    """pAliq só vai na DPS em município conveniado quando o prestador é ME/EPP do Simples com ISS pelo
    Simples e o ISS é retido (E0625 x regra A530). Nos demais casos com convênio ativo a alíquota vem
    da parametrização do município (E0617, E0635) e informar é rejeição. MEI e regime especial nunca
    informam (E0600, E0604)."""
    return p.op_simples == "3" and p.reg_ap_trib_sn == "1" and p.reg_esp_trib == "0" and iss_retido


def validar(d: DadosDps) -> None:
    """Regras que dá para conferir antes de enviar, com mensagens em português."""
    if d.valor <= 0:
        raise DpsInvalida("Informe o valor do serviço.")
    if d.desconto_incondicionado < 0 or d.desconto_incondicionado >= d.valor:
        raise DpsInvalida("O desconto deve ser menor que o valor do serviço.")
    r = d.retencoes
    if min(r.pis, r.cofins, r.csll, r.irrf, r.cp) < 0:
        raise DpsInvalida("Os valores retidos não podem ser negativos.")
    if d.prestador.op_simples == "2" and r.federais > 0:
        raise DpsInvalida("MEI não informa retenção de tributos federais (E0676).")
    for nome, v in (("INSS", r.cp), ("IRRF", r.irrf)):
        if v >= d.valor:
            raise DpsInvalida(f"A retenção de {nome} deve ser menor que o valor do serviço.")
    if r.federais >= d.valor - d.desconto_incondicionado:
        raise DpsInvalida("As retenções somadas não podem chegar ao valor do serviço.")
    if precisa_aliquota(d.prestador, r.iss):
        if d.aliquota_iss is None or not Decimal("0") < d.aliquota_iss <= Decimal("5"):
            raise DpsInvalida("Com ISS retido, a ME/EPP do Simples informa a alíquota efetiva de ISS (até 5%).")
    if d.competencia > (d.emitido_em or datetime.now(BRASILIA)).date():
        raise DpsInvalida("A competência não pode ser posterior à data de emissão (E0015).")
    if not d.descricao.strip():
        raise DpsInvalida("Informe a descrição do serviço.")
    if r.iss and (d.tomador is None or not d.tomador.tem_endereco):
        raise DpsInvalida("Com ISS retido, informe o tomador com endereço completo (E0237).")


def _e(pai, tag, texto=None):
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def montar(d: DadosDps) -> etree._Element:
    validar(d)
    restrita = d.ambiente == RESTRITA
    emitido = (d.emitido_em or datetime.now(BRASILIA)).astimezone(BRASILIA).replace(microsecond=0)
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(raiz, f"{{{NS}}}infDPS", Id=d.id_dps)
    _e(inf, "tpAmb", d.ambiente)
    _e(inf, "dhEmi", emitido.isoformat())
    _e(inf, "verAplic", VERSAO_APLICATIVO)
    _e(inf, "serie", int(d.serie))
    _e(inf, "nDPS", int(d.numero))
    _e(inf, "dCompet", d.competencia.isoformat())
    _e(inf, "tpEmit", 1)
    if restrita:
        _e(inf, "finNFSe", 0)  # NFS-e regular
    _e(inf, "cLocEmi", d.prestador.cod_municipio)

    p = _e(inf, "prest")
    _e(p, "CNPJ", d.prestador.cnpj)
    if d.prestador.inscricao_municipal:
        _e(p, "IM", d.prestador.inscricao_municipal)
    # xNome e endereço do prestador emitente não vão (E0121): vêm do cadastro nacional
    rt = _e(p, "regTrib")
    _e(rt, "opSimpNac", d.prestador.op_simples)
    if d.prestador.op_simples == "3":
        _e(rt, "regApTribSN", d.prestador.reg_ap_trib_sn or "1")
    _e(rt, "regEspTrib", d.prestador.reg_esp_trib)

    if d.tomador:
        t = d.tomador
        tm = _e(inf, "toma")
        _e(tm, "CNPJ" if len(t.documento) == 14 else "CPF", t.documento)
        if t.inscricao_municipal:
            _e(tm, "IM", t.inscricao_municipal)
        _e(tm, "xNome", t.nome[:300])
        if t.tem_endereco:
            end = _e(tm, "end")
            nac = _e(end, "endNac")
            _e(nac, "cMun", t.cod_municipio)
            _e(nac, "CEP", t.cep)
            _e(end, "xLgr", t.logradouro[:255])
            _e(end, "nro", t.numero[:60])
            if t.complemento:
                _e(end, "xCpl", t.complemento[:156])
            _e(end, "xBairro", t.bairro[:60])
        if t.telefone:
            _e(tm, "fone", t.telefone)
        if t.email:
            _e(tm, "email", t.email[:80])

    s = _e(inf, "serv")
    _e(_e(s, "locPrest"), "cLocPrestacao", d.cod_municipio_prestacao)
    cs = _e(s, "cServ")
    _e(cs, "cTribNac", d.ctribnac)
    if d.ctribmun:
        _e(cs, "cTribMun", d.ctribmun)
    if restrita:
        _e(cs, "cNBS", d.cnbs)
        _e(cs, "xDescServ", d.descricao[:2000])
    else:
        _e(cs, "xDescServ", d.descricao[:2000])
        _e(cs, "cNBS", d.cnbs)
    if d.info_complementar:
        _e(_e(s, "infoCompl"), "xInfComp", d.info_complementar[:2000])

    v = _e(inf, "valores")
    _e(_e(v, "vServPrest"), "vServ", _dec(d.valor))
    if d.desconto_incondicionado > 0:
        _e(_e(v, "vDescCondIncond"), "vDescIncond", _dec(d.desconto_incondicionado))
    tr = _e(v, "trib")
    tm = _e(tr, "tribMun")
    _e(tm, "tribISSQN", 1)  # operação tributável
    _e(tm, "tpRetISSQN", 2 if d.retencoes.iss else 1)  # 2 = retido pelo tomador
    if precisa_aliquota(d.prestador, d.retencoes.iss):
        _e(tm, "pAliq", _dec(d.aliquota_iss))
    r = d.retencoes
    if r.federais > 0:
        tf = _e(tr, "tribFed")
        if r.contribuicoes > 0:
            pc = _e(tf, "piscofins")
            _e(pc, "CST", "00")
            _e(pc, "tpRetPisCofins", r.tp_ret_pis_cofins)
        if r.cp > 0:
            _e(tf, "vRetCP", _dec(r.cp))
        if r.irrf > 0:
            _e(tf, "vRetIRRF", _dec(r.irrf))
        if r.contribuicoes > 0:
            _e(tf, "vRetCSLL", _dec(r.contribuicoes))
    tt = _e(tr, "totTrib")
    if d.prestador.op_simples == "3":
        # ME/EPP informa o percentual aproximado do Simples, nunca indTotTrib (E0712)
        _e(tt, "pTotTribSN", _dec(d.percentual_tributos_sn if d.percentual_tributos_sn is not None else Decimal("0")))
    else:
        _e(tt, "indTotTrib", 0)
    return raiz


@dataclass
class Cancelamento:
    ambiente: int
    cnpj_autor: str
    chave: str
    motivo: str        # 1 erro na emissão | 2 serviço não prestado | 9 outros
    justificativa: str
    emitido_em: datetime | None = None


def montar_cancelamento(c: Cancelamento) -> etree._Element:
    just = " ".join(c.justificativa.split())
    if c.motivo not in ("1", "2", "9"):
        raise DpsInvalida("Escolha o motivo do cancelamento.")
    if not 15 <= len(just) <= 255:
        raise DpsInvalida("A justificativa do cancelamento deve ter de 15 a 255 caracteres.")
    quando = (c.emitido_em or datetime.now(BRASILIA)).astimezone(BRASILIA).replace(microsecond=0) - timedelta(seconds=30)
    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(raiz, f"{{{NS}}}infPedReg", Id=f"PRE{c.chave}101101")
    for tag, val in (("tpAmb", c.ambiente), ("verAplic", VERSAO_APLICATIVO), ("dhEvento", quando.isoformat()),
                     ("CNPJAutor", c.cnpj_autor), ("chNFSe", c.chave)):
        _e(inf, tag, val)
    ev = _e(inf, "e101101")
    _e(ev, "xDesc", "Cancelamento de NFS-e")
    _e(ev, "cMotivo", c.motivo)
    _e(ev, "xMotivo", just)
    return raiz


@lru_cache
def _schema(ambiente: int, arquivo: str) -> etree.XMLSchema:
    pasta = XSD / ("restrita" if ambiente == RESTRITA else "producao")
    return etree.XMLSchema(etree.parse(str(pasta / arquivo)))


def validar_xsd(raiz, ambiente: int, arquivo: str = "DPS_v1.01.xsd") -> None:
    schema = _schema(ambiente, arquivo)
    if not schema.validate(raiz):
        erros = "; ".join(f"{e.message}" for e in list(schema.error_log)[:3])
        raise DpsInvalida(f"O XML não passou na validação do esquema oficial: {erros}")


def serializar(raiz) -> bytes:
    """A declaração XML com UTF-8 é obrigatória (sem ela a Sefin devolve E1229)."""
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
