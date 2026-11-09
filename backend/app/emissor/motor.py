"""Motor de emissão: numeração, montagem, envio, recuperação e cancelamento de NFS-e.

Regras de segurança:
- O número da DPS é reservado e gravado ANTES do envio. Nunca se reaproveita um número que possa ter
  gerado nota: o reenvio de uma nota pendente/rejeitada usa a mesma DPS (mesmo Id), e a Sefin recusa
  duplicidade (E0014), então não existe nota duplicada.
- Depois de falha de rede, o resultado é desconhecido: consulta-se /dps/{id} antes de qualquer reenvio.
- Ambiente: produção restrita, salvo CONTASK_EMISSOR_PRODUCAO=true E a empresa com producao_liberada.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.core.certificados import carregar_pfx, situacao_validade
from app.core.config import config
from app.emissor import assinatura
from app.emissor.dps import (
    BRASILIA, PRODUCAO, RESTRITA, Cancelamento, DadosDps, DpsInvalida, Prestador, Retencoes, TomadorDps,
    centavos, id_dps, montar, montar_cancelamento, serializar, validar_xsd,
)
from app.emissor.sefin import ClienteSefin, ErroSefin
from app.fiscal.parser import parse_nfse
from app.models import EmissorEmpresa, Empresa, NotaEmitida, ServicoEmissor, agora

log = logging.getLogger("contask.emissor")

_travas: dict[int, threading.Lock] = defaultdict(threading.Lock)
_trava_dict = threading.Lock()


def _trava(empresa_id: int) -> threading.Lock:
    with _trava_dict:
        return _travas[empresa_id]


def producao_disponivel() -> bool:
    """Chave geral do sistema (CONTASK_EMISSOR_PRODUCAO)."""
    return bool(config().emissor_producao)


def ambiente(cfg: EmissorEmpresa | None = None) -> int:
    """Produção só com a chave geral ligada e a empresa liberada; o resto vai para a produção restrita."""
    if producao_disponivel() and cfg is not None and cfg.producao_liberada:
        return PRODUCAO
    return RESTRITA


# Injetável nos testes
FabricaCliente = Callable[[int, bytes, str], ClienteSefin]
fabrica_cliente: FabricaCliente = lambda amb, pfx, senha: ClienteSefin(ambiente=amb, pfx=pfx, senha=senha)  # noqa: E731


class ErroEmissao(Exception):
    """Mensagem pensada para ser mostrada ao usuário."""

    def __init__(self, mensagem: str, status: int = 422):
        super().__init__(mensagem)
        self.status = status


@dataclass
class Entrada:
    empresa_id: int
    servico_id: int | None
    descricao: str | None
    competencia: date
    valor: Decimal
    tomador: dict | None = None          # campos já validados (ver api.emissor._validar_tomador)
    salvar_tomador: bool = True
    desconto: Decimal = Decimal("0")
    iss_retido: bool = False
    aliquota_iss: Decimal | None = None
    ret_pis: Decimal = Decimal("0")
    ret_cofins: Decimal = Decimal("0")
    ret_csll: Decimal = Decimal("0")
    ret_irrf: Decimal = Decimal("0")
    ret_cp: Decimal = Decimal("0")
    cod_municipio_prestacao: str | None = None
    info_complementar: str | None = None
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------

def _empresa_pronta(db: Session, esc: int, empresa_id: int) -> tuple[Empresa, EmissorEmpresa]:
    from app.api.emissor import certificado_emissor, config_prestador, emite_por_procuracao
    e = db.get(Empresa, empresa_id)
    if e is None or e.escritorio_id != esc:
        raise ErroEmissao("Empresa não encontrada.", 404)
    if not e.emite_nfse:
        raise ErroEmissao("Esta empresa não está marcada para emitir NFS-e pelo Contask.")
    if not e.ativa:
        raise ErroEmissao("A empresa está inativa.")
    cert = certificado_emissor(db, e)
    if cert is None:
        raise ErroEmissao("Cadastre o certificado A1 da empresa ou o da contabilidade (procuração).")
    if situacao_validade(cert.validade) == "vencido":
        raise ErroEmissao(f"O certificado da empresa venceu em {cert.validade:%d/%m/%Y}.")
    cfg = config_prestador(db, e)
    if emite_por_procuracao(db, e) and ambiente(cfg) == RESTRITA:
        # Barrado antes de gastar número: a produção restrita não reconhece procurações
        raise ErroEmissao("Na homologação a Sefin recusa a emissão por procuração (E0718). Libere a produção "
                          "para esta empresa ou cadastre o certificado A1 dela.")
    if not cfg.cod_municipio:
        ibge = (e.dados_brasilapi or {}).get("codigo_municipio_ibge")
        if ibge:
            cfg.cod_municipio = str(ibge)
    if not cfg.cod_municipio:
        raise ErroEmissao("Informe o município da empresa (código IBGE) nos dados do prestador.")
    return e, cfg


def _dados(e: Empresa, cfg: EmissorEmpresa, nota: NotaEmitida) -> DadosDps:
    t = nota.tomador
    return DadosDps(
        ambiente=nota.ambiente, serie=nota.serie, numero=nota.numero, competencia=nota.competencia,
        prestador=Prestador(cnpj=e.cnpj, cod_municipio=cfg.cod_municipio, op_simples=cfg.op_simples,
                            reg_ap_trib_sn=cfg.reg_ap_trib_sn, reg_esp_trib=cfg.reg_esp_trib,
                            inscricao_municipal=cfg.inscricao_municipal),
        tomador=TomadorDps(**{k: t.get(k) for k in TomadorDps.__dataclass_fields__}) if t else None,
        ctribnac=nota.ctribnac, cnbs=nota.cnbs, ctribmun=nota.ctribmun, descricao=nota.descricao,
        valor=centavos(nota.valor_servico), desconto_incondicionado=centavos(nota.desconto),
        cod_municipio_prestacao=nota.cod_municipio_prestacao,
        aliquota_iss=nota.aliquota_iss,
        retencoes=Retencoes(iss=nota.iss_retido, pis=centavos(nota.ret_pis), cofins=centavos(nota.ret_cofins),
                            csll=centavos(nota.ret_csll), irrf=centavos(nota.ret_irrf), cp=centavos(nota.ret_cp)),
        percentual_tributos_sn=cfg.percentual_tributos, info_complementar=nota.info_complementar,
    )


def _preencher(db: Session, nota: NotaEmitida, e: Empresa, cfg: EmissorEmpresa, ent: Entrada) -> None:
    serv = None
    if ent.servico_id:
        serv = db.get(ServicoEmissor, ent.servico_id)
        if serv is None or serv.empresa_id != e.id:
            raise ErroEmissao("Serviço não encontrado para esta empresa.", 404)
    if serv is None:
        raise ErroEmissao("Escolha o serviço (ou cadastre um novo).")
    descricao = (ent.descricao or "").strip() or serv.descricao
    nota.servico_id = serv.id
    nota.ctribnac, nota.cnbs, nota.ctribmun = serv.ctribnac, serv.cnbs, serv.ctribmun
    nota.descricao = descricao
    nota.competencia = ent.competencia
    nota.tomador = ent.tomador
    nota.cod_municipio_prestacao = ent.cod_municipio_prestacao or cfg.cod_municipio
    nota.valor_servico, nota.desconto = centavos(ent.valor), centavos(ent.desconto)
    nota.iss_retido = ent.iss_retido
    nota.aliquota_iss = Decimal(str(ent.aliquota_iss)) if ent.aliquota_iss is not None else None
    nota.ret_pis, nota.ret_cofins, nota.ret_csll = centavos(ent.ret_pis), centavos(ent.ret_cofins), centavos(ent.ret_csll)
    nota.ret_irrf, nota.ret_cp = centavos(ent.ret_irrf), centavos(ent.ret_cp)
    nota.info_complementar = (ent.info_complementar or "").strip() or None


def _xml_assinado(db: Session, e: Empresa, cfg: EmissorEmpresa, nota: NotaEmitida) -> bytes:
    from app.api.emissor import certificado_emissor
    raiz = montar(_dados(e, cfg, nota))
    pfx, senha = carregar_pfx(certificado_emissor(db, e))
    chave, cert = assinatura.carregar_chave(pfx, senha)
    assinatura.assinar(raiz, raiz[0], chave, cert)
    validar_xsd(raiz, nota.ambiente)
    return serializar(raiz)


def _pasta(e: Empresa, amb: int) -> Path:
    p = config().dados_dir / "empresas" / e.cnpj / "emitidas" / ("producao" if amb == PRODUCAO else "homologacao")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _gravar(e: Empresa, amb: int, nome: str, conteudo: bytes) -> str:
    destino = _pasta(e, amb) / nome
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(conteudo)
    tmp.replace(destino)
    return destino.relative_to(config().dados_dir).as_posix()


def _salvar_tomador(db: Session, esc: int, dados: dict | None) -> None:
    from sqlalchemy import select
    from app.models import Tomador
    if not dados:
        return
    t = db.scalar(select(Tomador).where(Tomador.escritorio_id == esc, Tomador.documento == dados["documento"]))
    if t is None:
        t = Tomador(escritorio_id=esc)
        db.add(t)
    for k, v in dados.items():
        setattr(t, k, v)


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

def _autorizar(db: Session, e: Empresa, nota: NotaEmitida, xml: bytes, chave: str | None) -> None:
    d = parse_nfse(xml)
    nota.chave = d.chave or chave
    nota.numero_nfse = d.numero
    nota.valor_iss, nota.valor_liquido = d.valor_iss, d.valor_liquido
    nota.xml_nfse_path = _gravar(e, nota.ambiente, f"NFSe_{nota.chave}.xml", xml)
    nota.situacao, nota.erros, nota.mensagem = "autorizada", None, None
    nota.autorizado_em = agora()


def _enviar(db: Session, e: Empresa, nota: NotaEmitida, xml: bytes) -> None:
    from app.api.emissor import certificado_emissor
    pfx, senha = carregar_pfx(certificado_emissor(db, e))
    nota.enviado_em = agora()
    with fabrica_cliente(nota.ambiente, pfx, senha) as cli:
        try:
            r = cli.emitir(xml)
        except ErroSefin as ex:
            log.warning("Emissão %s sem resposta: %s", nota.id_dps, ex)
            _recuperar(cli, db, e, nota, motivo=str(ex))
            return
        if r.ok:
            _autorizar(db, e, nota, r.xml, r.chave)
            return
        if any(x.get("codigo") == "E0014" for x in r.erros):
            # Já existe NFS-e para esta DPS: foi gerada numa tentativa anterior sem resposta
            if _recuperar(cli, db, e, nota, motivo="A Sefin informou que a DPS já gerou uma nota.") == "autorizada":
                return
        nota.situacao, nota.erros = "rejeitada", r.erros
        nota.mensagem = "; ".join(f"{x.get('codigo')}: {x.get('descricao')}" for x in r.erros)


def _recuperar(cli: ClienteSefin, db: Session, e: Empresa, nota: NotaEmitida, motivo: str) -> str:
    """autorizada | nao_gerada | desconhecido"""
    try:
        chave = cli.chave_da_dps(nota.id_dps)
        if chave:
            _autorizar(db, e, nota, cli.obter_nfse(chave), chave)
            return "autorizada"
        nota.situacao = "pendente"
        nota.mensagem = f"{motivo} Nenhuma nota foi gerada: pode reenviar."
        return "nao_gerada"
    except ErroSefin as ex:
        nota.situacao = "pendente"
        nota.mensagem = f"{motivo} Não foi possível confirmar o resultado ({ex}). Verifique antes de reenviar."
        return "desconhecido"


# ---------------------------------------------------------------------------
# Operações
# ---------------------------------------------------------------------------

def emitir(db: Session, esc: int, usuario_id: int | None, ent: Entrada) -> NotaEmitida:
    e, cfg = _empresa_pronta(db, esc, ent.empresa_id)
    amb = ambiente(cfg)
    nota = NotaEmitida(escritorio_id=esc, empresa_id=e.id, usuario_id=usuario_id, ambiente=amb, serie=cfg.serie,
                       numero=0, id_dps="", situacao="enviando")
    _preencher(db, nota, e, cfg, ent)
    # Valida tudo (regras e XSD) antes de gastar um número
    try:
        nota.numero = cfg.proximo_numero
        _xml_assinado(db, e, cfg, nota)
    except DpsInvalida as ex:
        db.rollback()
        raise ErroEmissao(str(ex)) from None

    with _trava(e.id):
        db.refresh(cfg)
        nota.numero = cfg.proximo_numero
        nota.serie = cfg.serie
        nota.id_dps = id_dps(cfg.cod_municipio, e.cnpj, cfg.serie, nota.numero)
        cfg.proximo_numero = nota.numero + 1
        if ent.salvar_tomador:
            _salvar_tomador(db, esc, ent.tomador)
        db.add(nota)
        db.commit()  # número reservado antes de enviar

    xml = _xml_assinado(db, e, cfg, nota)
    nota.xml_dps_path = _gravar(e, amb, f"{nota.id_dps}.xml", xml)
    _enviar(db, e, nota, xml)
    db.commit()
    return nota


def _nota(db: Session, esc: int, nota_id: int) -> NotaEmitida:
    n = db.get(NotaEmitida, nota_id)
    if n is None or n.escritorio_id != esc:
        raise ErroEmissao("Nota não encontrada.", 404)
    return n


def reenviar(db: Session, esc: int, nota_id: int, ent: Entrada | None) -> NotaEmitida:
    """Rejeitada: corrige e reenvia com o MESMO número. Pendente: confere na Sefin e, se não gerou, reenvia."""
    nota = _nota(db, esc, nota_id)
    if nota.situacao not in ("rejeitada", "pendente"):
        raise ErroEmissao("Só dá para reenviar uma nota rejeitada ou com resultado pendente.", 409)
    e, cfg = _empresa_pronta(db, esc, nota.empresa_id)
    if nota.ambiente != ambiente(cfg):
        raise ErroEmissao("Esta nota é de outro ambiente (homologação x produção).", 409)
    if nota.situacao == "pendente":
        from app.api.emissor import certificado_emissor
        pfx, senha = carregar_pfx(certificado_emissor(db, e))
        with fabrica_cliente(nota.ambiente, pfx, senha) as cli:
            resultado = _recuperar(cli, db, e, nota, motivo="Conferência antes do reenvio.")
        if resultado != "nao_gerada":
            db.commit()
            return nota
    if ent is not None:
        if ent.empresa_id != nota.empresa_id:
            raise ErroEmissao("A empresa de uma nota não pode ser trocada no reenvio.")
        _preencher(db, nota, e, cfg, ent)
        if ent.salvar_tomador:
            _salvar_tomador(db, esc, ent.tomador)
    try:
        xml = _xml_assinado(db, e, cfg, nota)
    except DpsInvalida as ex:
        db.rollback()
        raise ErroEmissao(str(ex)) from None
    nota.situacao, nota.erros, nota.mensagem = "enviando", None, None
    nota.xml_dps_path = _gravar(e, nota.ambiente, f"{nota.id_dps}.xml", xml)
    db.commit()
    _enviar(db, e, nota, xml)
    db.commit()
    return nota


def cancelar(db: Session, esc: int, nota_id: int, motivo: str, justificativa: str) -> NotaEmitida:
    nota = _nota(db, esc, nota_id)
    if nota.situacao != "autorizada" or not nota.chave:
        raise ErroEmissao("Só dá para cancelar uma nota autorizada.", 409)
    from app.api.emissor import certificado_proprio
    e = db.get(Empresa, nota.empresa_id)
    cert = certificado_proprio(db, e)  # por procuração a Sefin recusa o evento (E0812/E0813)
    if cert is None:
        raise ErroEmissao("A Sefin não aceita cancelamento por procuração. Cancele pelo Emissor Nacional Web "
                          "(Procuração/Representação) ou cadastre o certificado A1 da empresa.", 409)
    try:
        raiz = montar_cancelamento(Cancelamento(ambiente=nota.ambiente, cnpj_autor=e.cnpj, chave=nota.chave,
                                                motivo=motivo, justificativa=justificativa))
        pfx, senha = carregar_pfx(cert)
        chave, c = assinatura.carregar_chave(pfx, senha)
        assinatura.assinar(raiz, raiz[0], chave, c)
        validar_xsd(raiz, nota.ambiente, "pedRegEvento_v1.01.xsd")
    except DpsInvalida as ex:
        raise ErroEmissao(str(ex)) from None
    with fabrica_cliente(nota.ambiente, pfx, senha) as cli:
        try:
            r = cli.registrar_evento(nota.chave, serializar(raiz))
        except ErroSefin as ex:
            raise ErroEmissao(f"{ex} Confira a nota antes de tentar de novo.", 502) from None
    if not r.ok:
        raise ErroEmissao("A Sefin recusou o cancelamento: " +
                          "; ".join(f"{x.get('codigo')}: {x.get('descricao')}" for x in r.erros))
    nota.xml_cancelamento_path = _gravar(e, nota.ambiente, f"EVT_{nota.chave}_101101.xml", r.xml)
    nota.situacao, nota.cancelado_em = "cancelada", agora()
    nota.motivo_cancelamento = " ".join(justificativa.split())
    db.commit()
    return nota
