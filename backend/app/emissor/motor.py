"""Motor de emissão: numeração, montagem, envio, recuperação e cancelamento de NFS-e.

Regras de segurança:
- O número da DPS é reservado e gravado ANTES do envio. Nunca se reaproveita um número que possa ter
  gerado nota: o reenvio de uma nota pendente/rejeitada usa a mesma DPS (mesmo Id), e a Sefin recusa
  duplicidade (E0014), então não existe nota duplicada.
- Depois de falha de rede, o resultado é desconhecido: consulta-se /dps/{id} antes de qualquer reenvio.
- Ambiente: produção restrita, salvo CONTASK_EMISSOR_PRODUCAO=true E a empresa com producao_liberada.
- Canal: empresa do DF fora do Simples emite pelo webservice do ISSNet do DF; as demais pela Sefin Nacional.
  No ISSNet o número da DPS (RPS) é do fisco: vem da lista de RPS disponíveis (issnet.rps), reservado antes do
  envio. Depois de falha de rede consulta-se ConsultarNfseDps antes de qualquer reenvio.
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

from lxml import etree
from sqlalchemy.orm import Session

from app.core.certificados import carregar_pfx, situacao_validade
from app.core.config import config
from app.emissor import assinatura, textos
from app.emissor.dps import (
    BRASILIA, NT004, NT009, PRODUCAO, RESTRITA, Cancelamento, DadosDps, DpsInvalida, Prestador, Retencoes,
    Substituicao, TomadorDps, centavos, gravar_leiaute_producao, id_dps, leiaute_do_ambiente, montar, montar_cancelamento,
    montar_issnet, serializar, validar_xsd, validar_xsd_issnet,
)
from app.emissor.issnet import mensagens as issnet_msg
from app.emissor.issnet import rps as issnet_rps
from app.emissor.issnet.soap import ClienteIssnet, ErroIssnet
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
    """Produção só com a chave geral ligada e a empresa liberada; o resto vai para a produção restrita.
    O ISSNet do DF não tem homologação para o Contask (decisão de 15/11/2026): é sempre produção."""
    if producao_disponivel() and cfg is not None and (cfg.producao_liberada or canal(cfg) == ISSNET_DF):
        return PRODUCAO
    return RESTRITA


def eh_simples(cfg: EmissorEmpresa | None) -> bool:
    """Regime escolhido no cadastro; sem ele, a situação no Simples da DPS (MEI ou ME/EPP)."""
    if cfg is None:
        return False
    if cfg.regime_tributario:
        return cfg.regime_tributario == "simples"
    return cfg.op_simples in ("2", "3")


BRASILIA = "5300108"

NACIONAL, ISSNET_DF = "nacional", "issnet_df"


def canal(cfg: EmissorEmpresa | None) -> str:
    """Por onde a nota sai: ISSNet do DF para empresa do DF fora do Simples; Sefin Nacional no resto."""
    if cfg is not None and cfg.cod_municipio == BRASILIA and not eh_simples(cfg):
        return ISSNET_DF
    return NACIONAL


def pendencia_canal(db: Session, e: Empresa, cfg: EmissorEmpresa | None) -> str | None:
    """O que falta para emitir pelo ISSNet do DF (None quando o canal é a Sefin ou está tudo certo)."""
    from app.api.emissor import certificado_emissor
    if canal(cfg) != ISSNET_DF:
        return None
    if not producao_disponivel():
        return ("No DF, empresa fora do Simples emite pelo ISSNet, que não tem homologação: a emissão em produção "
                "está desligada neste sistema (CONTASK_EMISSOR_PRODUCAO).")
    if certificado_emissor(db, e) is None:
        # Procuração vale: em 15/11/2026 o ISSNet de produção aceitou emissão e cancelamento assinados pelo
        # certificado do procurador (CONTOUCH pela VCS, NFS-e 180), embora o manual peça o da empresa
        return "Cadastre o certificado A1 da empresa ou use a procuração (certificado da contabilidade)."
    if not (cfg.inscricao_municipal or "").strip():
        return "Informe a inscrição municipal nos dados do prestador: o ISSNet do DF exige."
    return None


# Injetável nos testes
FabricaCliente = Callable[[int, bytes, str], ClienteSefin]
fabrica_cliente: FabricaCliente = lambda amb, pfx, senha: ClienteSefin(ambiente=amb, pfx=pfx, senha=senha)  # noqa: E731
FabricaIssnet = Callable[[int, bytes, str], ClienteIssnet]
fabrica_issnet: FabricaIssnet = lambda amb, pfx, senha: ClienteIssnet(ambiente=amb, pfx=pfx, senha=senha)  # noqa: E731


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
    texto_simples: bool = True    # só vale para empresa do Simples
    texto_procon: bool = True
    texto_fixo: bool = True       # texto fixo da empresa (dados bancários etc.), quando houver
    recorrente_id: int | None = None
    servico_codigos: dict | None = None  # sem serviço cadastrado: ctribnac, cnbs, ctribmun, cindop, cclasstrib
    extras: dict = field(default_factory=dict)
    # Substituição: {"nota_id": nota do Contask} ou {"nota_adn_id": nota prestada vinda do ADN}, mais motivo e
    # justificativa (ver dps.MOTIVOS_SUBSTITUICAO)
    substituicao: dict | None = None


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
    if canal(cfg) == NACIONAL and emite_por_procuracao(db, e) and ambiente(cfg) == RESTRITA:
        # Barrado antes de gastar número: a produção restrita não reconhece procurações
        raise ErroEmissao("Na homologação a Sefin recusa a emissão por procuração (E0718). Escolha Produção no ambiente "
                          "de emissão desta empresa ou cadastre o certificado A1 dela.")
    from app.emissor.municipio import garantir_municipio
    municipio_ok = garantir_municipio(db, e, cfg)
    pend = pendencia_canal(db, e, cfg)
    if pend:
        raise ErroEmissao(pend)  # barrado antes de gastar número
    if not municipio_ok:
        raise ErroEmissao("Não foi possível descobrir o código IBGE do município da empresa. Confira o município e a UF "
                          "no cadastro da empresa ou informe o código nos dados do prestador.")
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
        cindop=nota.cindop, cclasstrib=nota.cclasstrib,
        subst=Substituicao(nota.subst_chave, nota.subst_motivo or "", nota.subst_justificativa or "")
        if nota.subst_chave else None,
    )


def _substituida(db: Session, esc: int, e: Empresa, amb: int, sub: dict) -> tuple[str, NotaEmitida | None]:
    """Chave da NFS-e a substituir (e a nota do Contask, quando é dele). Só nota autorizada da mesma empresa."""
    from sqlalchemy import select
    from app.models import Nota
    original = None
    if sub.get("nota_id"):
        original = db.get(NotaEmitida, sub["nota_id"])
        if original is None or original.escritorio_id != esc or original.empresa_id != e.id:
            raise ErroEmissao("Nota a substituir não encontrada para esta empresa.", 404)
        if original.situacao != "autorizada" or not original.chave:
            raise ErroEmissao("Só dá para substituir uma nota autorizada.", 409)
        if original.ambiente != amb:
            raise ErroEmissao("A nota a substituir é de outro ambiente (homologação x produção).", 409)
        chave = original.chave
    elif sub.get("nota_adn_id"):
        n = db.get(Nota, sub["nota_adn_id"])
        if n is None or n.empresa_id != e.id or n.papel != "prestada":
            raise ErroEmissao("Nota a substituir não encontrada entre as prestadas desta empresa.", 404)
        if n.status != "autorizada":
            raise ErroEmissao("Só dá para substituir uma nota autorizada.", 409)
        if amb != PRODUCAO:
            raise ErroEmissao("As notas do ADN são de produção: passe a empresa para produção para substituir.", 409)
        chave = n.chave
        original = db.scalar(select(NotaEmitida).where(NotaEmitida.chave == chave, NotaEmitida.empresa_id == e.id))
    else:
        raise ErroEmissao("Informe a nota a substituir.")
    andamento = db.scalar(select(NotaEmitida).where(
        NotaEmitida.subst_chave == chave, NotaEmitida.situacao.in_(("enviando", "pendente", "autorizada"))))
    if andamento is not None:
        raise ErroEmissao("Esta nota já tem uma substituta em andamento ou autorizada. Veja a lista de notas emitidas.", 409)
    return chave, original


def _concluir_substituicao(db: Session, nota: NotaEmitida) -> None:
    """Substituta autorizada: a Sefin cancela a original (evento 105102); a do Contask é marcada já."""
    if not nota.subst_chave:
        return
    from sqlalchemy import select
    original = db.scalar(select(NotaEmitida).where(
        NotaEmitida.chave == nota.subst_chave, NotaEmitida.empresa_id == nota.empresa_id,
        NotaEmitida.ambiente == nota.ambiente, NotaEmitida.id != nota.id))
    if original is None or original.situacao == "cancelada":
        return
    original.situacao, original.cancelado_em = "cancelada", agora()
    original.substituida_por_id = nota.id
    original.motivo_cancelamento = (f"Substituída pela NFS-e nº {nota.numero_nfse or '-'}: "
                                    f"{' '.join((nota.subst_justificativa or '').split())}")
    original.mensagem = None


def _preencher(db: Session, nota: NotaEmitida, e: Empresa, cfg: EmissorEmpresa, ent: Entrada) -> None:
    serv = None
    if ent.servico_id:
        serv = db.get(ServicoEmissor, ent.servico_id)
        if serv is None or serv.empresa_id != e.id:
            raise ErroEmissao("Serviço não encontrado para esta empresa.", 404)
    if serv is not None:
        codigos = {k: getattr(serv, k) for k in ("ctribnac", "cnbs", "ctribmun", "cindop", "cclasstrib")}
    elif ent.servico_codigos:
        codigos = ent.servico_codigos
    else:
        raise ErroEmissao("Escolha o serviço (ou cadastre um novo).")
    descricao = (ent.descricao or "").strip() or (serv.descricao if serv else "")
    if not descricao:
        raise ErroEmissao("Informe a descrição do serviço.")
    nota.servico_id = serv.id if serv else None
    nota.ctribnac, nota.cnbs, nota.ctribmun = codigos["ctribnac"], codigos["cnbs"], codigos.get("ctribmun")
    nota.cindop, nota.cclasstrib = codigos.get("cindop"), codigos.get("cclasstrib")
    nota.descricao = descricao
    nota.competencia = ent.competencia
    nota.tomador = ent.tomador
    nota.cod_municipio_prestacao = ent.cod_municipio_prestacao or cfg.cod_municipio
    nota.valor_servico, nota.desconto = centavos(ent.valor), centavos(ent.desconto)
    nota.iss_retido = ent.iss_retido
    nota.aliquota_iss = Decimal(str(ent.aliquota_iss)) if ent.aliquota_iss is not None else None
    nota.ret_pis, nota.ret_cofins, nota.ret_csll = centavos(ent.ret_pis), centavos(ent.ret_cofins), centavos(ent.ret_csll)
    nota.ret_irrf, nota.ret_cp = centavos(ent.ret_irrf), centavos(ent.ret_cp)
    try:
        nota.info_complementar = textos.compor(ent.info_complementar, ent.texto_simples and eh_simples(cfg), ent.texto_procon,
                                               cfg.texto_fixo if ent.texto_fixo else None)
    except ValueError as ex:
        raise ErroEmissao(str(ex)) from None


def _xml_assinado(db: Session, e: Empresa, cfg: EmissorEmpresa, nota: NotaEmitida, leiaute: str | None = None) -> bytes:
    from app.api.emissor import certificado_emissor
    if nota.canal == ISSNET_DF:
        raiz = montar_issnet(_dados(e, cfg, nota))
        pfx, senha = carregar_pfx(certificado_emissor(db, e))
        chave, cert = assinatura.carregar_chave(pfx, senha)
        assinatura.assinar(raiz, raiz[0], chave, cert, perfil=PERFIS_ISSNET[0])
        validar_xsd_issnet(etree.fromstring(issnet_msg.gerar_nfse(raiz).encode("utf-8")))
        return serializar(raiz)
    raiz = montar(_dados(e, cfg, nota), leiaute)
    pfx, senha = carregar_pfx(certificado_emissor(db, e))
    chave, cert = assinatura.carregar_chave(pfx, senha)
    assinatura.assinar(raiz, raiz[0], chave, cert)
    validar_xsd(raiz, nota.ambiente, leiaute=leiaute)
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
    _concluir_substituicao(db, nota)


ERROS_ESQUEMA = {"E1235"}


def erro_de_esquema(erros: list[dict]) -> bool:
    """Recusa do XML pelo esquema da Sefin (nenhuma nota é gerada)."""
    for x in erros:
        texto = f"{x.get('descricao') or ''} {x.get('complemento') or ''}".lower()
        if x.get("codigo") in ERROS_ESQUEMA or "schema" in texto or "esquema" in texto:
            return True
    return False


def _enviar(db: Session, e: Empresa, nota: NotaEmitida, xml: bytes, cfg: EmissorEmpresa | None = None) -> None:
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
        if not r.ok and cfg is not None and nota.ambiente == PRODUCAO and erro_de_esquema(r.erros):
            # A produção troca da NT 004 para a NT 009 (anunciado para depois de 30/11/2026). Recusa por
            # esquema não gera nota: monta no outro leiaute e envia uma vez, com o mesmo número.
            outro = NT009 if leiaute_do_ambiente(PRODUCAO) == NT004 else NT004
            try:
                xml2 = _xml_assinado(db, e, cfg, nota, outro)
            except DpsInvalida:
                xml2 = None
            if xml2 is not None:
                log.warning("Produção recusou a DPS %s por esquema; tentando o leiaute %s.", nota.id_dps, outro)
                try:
                    r2 = cli.emitir(xml2)
                except ErroSefin as ex:
                    log.warning("Emissão %s sem resposta: %s", nota.id_dps, ex)
                    nota.xml_dps_path = _gravar(e, nota.ambiente, f"{nota.id_dps}.xml", xml2)
                    _recuperar(cli, db, e, nota, motivo=str(ex))
                    return
                if r2.ok or not erro_de_esquema(r2.erros):
                    gravar_leiaute_producao(outro)
                    log.warning("Leiaute da produção passou a ser %s.", outro)
                    nota.xml_dps_path = _gravar(e, nota.ambiente, f"{nota.id_dps}.xml", xml2)
                    r = r2
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
# Envio pelo ISSNet do DF
# ---------------------------------------------------------------------------

def _cliente_issnet(db: Session, e: Empresa, amb: int) -> ClienteIssnet:
    from app.api.emissor import certificado_emissor
    pfx, senha = carregar_pfx(certificado_emissor(db, e))
    return fabrica_issnet(amb, pfx, senha)


def _alertas(r) -> str | None:
    return "; ".join(f"{x.get('codigo')}: {x.get('descricao')}" for x in r.alertas) or None


ERRO_ASSINATURA = "E0714"
# O manual da Nota Control pede C14N inclusiva + RSA-SHA1, mas a produção do DF (15/11/2026) recusou esse perfil
# com E0714 e aceitou C14N exclusiva + RSA-SHA256 (o da Sefin). O outro fica de reserva: E0714 não gera nota,
# então reenviar com o outro perfil é seguro.
PERFIS_ISSNET = (assinatura.SEFIN, assinatura.ISSNET)


def _assinador_no_envelope(db: Session, e: Empresa, nota: NotaEmitida, perfil=assinatura.ISSNET):
    """Assina a DPS já dentro do envelope SOAP. A primeira emissão real (15/11/2026) com a DPS assinada à parte
    voltou E0714: o ISSNet confere a assinatura (C14N inclusiva) no próprio envelope, com os namespaces dele."""
    from app.api.emissor import certificado_emissor
    pfx, senha = carregar_pfx(certificado_emissor(db, e))
    chave, cert = assinatura.carregar_chave(pfx, senha)

    def assinar(envio) -> None:
        dps = envio[0]
        for s in dps.findall(f"{{{assinatura.DS}}}Signature"):
            dps.remove(s)
        assinatura.assinar(dps, dps[0], chave, cert, perfil=perfil)
        # A cópia gravada leva as declarações do envelope e continua conferível sozinha
        nota.xml_dps_path = _gravar(e, nota.ambiente, f"{nota.id_dps}.xml",
                                    etree.tostring(dps, xml_declaration=True, encoding="UTF-8"))
    return assinar


def _enviar_issnet(db: Session, e: Empresa, cfg: EmissorEmpresa, nota: NotaEmitida, xml: bytes) -> None:
    nota.enviado_em = agora()
    with _cliente_issnet(db, e, nota.ambiente) as cli:
        for perfil in PERFIS_ISSNET:
            try:
                r = cli.chamar("GerarNfse", issnet_msg.gerar_nfse(etree.fromstring(xml)),
                               assinar=_assinador_no_envelope(db, e, nota, perfil))
            except ErroIssnet as ex:
                log.warning("Emissão ISSNet %s sem resposta: %s", nota.id_dps, ex)
                _recuperar_issnet(cli, db, e, cfg, nota, motivo=str(ex))
                return
            if not any(x.get("codigo") == ERRO_ASSINATURA for x in r.erros):
                break
            log.warning("ISSNet recusou a assinatura (%s) da DPS %s", perfil.digest, nota.id_dps)
        notas = issnet_msg.nfses(r)
        if r.ok and notas:
            _autorizar(db, e, nota, notas[0], None)
            nota.mensagem = _alertas(r)
            issnet_rps.concluir(db, nota.id, autorizada=True)
            return
        if r.ok:
            # Resposta sem NFS-e e sem erro: confere pela DPS antes de dar qualquer resultado
            _recuperar_issnet(cli, db, e, cfg, nota, motivo="O ISSNet não devolveu a nota.")
            return
        nota.situacao, nota.erros = "rejeitada", r.erros
        nota.mensagem = issnet_msg.texto_erros(r.erros)


def _recuperar_issnet(cli: ClienteIssnet, db: Session, e: Empresa, cfg: EmissorEmpresa, nota: NotaEmitida,
                      motivo: str) -> str:
    """autorizada | nao_gerada | desconhecido (mesma regra da Sefin: nunca reenviar às cegas)."""
    try:
        r = cli.chamar("ConsultarNfseDps", issnet_msg.consultar_nfse_por_dps(
            e.cnpj, cfg.inscricao_municipal, nota.serie, nota.numero))
    except ErroIssnet as ex:
        nota.situacao = "pendente"
        nota.mensagem = f"{motivo} Não foi possível confirmar o resultado ({ex}). Verifique antes de reenviar."
        return "desconhecido"
    notas = issnet_msg.nfses(r)
    if notas:
        _autorizar(db, e, nota, notas[0], None)
        issnet_rps.concluir(db, nota.id, autorizada=True)
        return "autorizada"
    nota.situacao = "pendente"
    if r.erros:
        nota.mensagem = (f"{motivo} O ISSNet não encontrou nota para esta DPS "
                         f"({issnet_msg.texto_erros(r.erros)}): pode reenviar.")
        return "nao_gerada"
    nota.mensagem = f"{motivo} Resposta inesperada do ISSNet na conferência. Verifique antes de reenviar."
    return "desconhecido"


def _reservar_rps(db: Session, e: Empresa, cfg: EmissorEmpresa, amb: int, nota: NotaEmitida) -> None:
    """Chamado com a trava da empresa: sincroniza a lista se estiver velha e reserva o menor número livre."""
    if issnet_rps.precisa_sincronizar(db, e.id, amb):
        with _cliente_issnet(db, e, amb) as cli:
            issnet_rps.sincronizar(db, e.id, e.cnpj, cfg.inscricao_municipal, amb, cli)
    try:
        r = issnet_rps.reservar(db, e.id, amb)
    except issnet_rps.SemRps as ex:
        sinc = issnet_rps.ultima_sincronizacao(db, e.id, amb)
        detalhe = f" Última leitura com erro: {sinc.erro}" if sinc is not None and sinc.erro else ""
        raise ErroEmissao(f"{ex}{detalhe}") from None
    nota.serie, nota.numero = r.serie, r.numero
    nota.id_dps = id_dps(cfg.cod_municipio, e.cnpj, r.serie, r.numero)
    db.add(nota)
    db.flush()
    r.nota_id = nota.id


# ---------------------------------------------------------------------------
# Operações
# ---------------------------------------------------------------------------

def emitir(db: Session, esc: int, usuario_id: int | None, ent: Entrada) -> NotaEmitida:
    from app.core.escritorios import em_teste, emissoes_do_escritorio
    # No teste grátis, substituir a nota já emitida pelo Contask não conta como emissão nova
    corrige = bool(ent.substituicao and ent.substituicao.get("nota_id"))
    if not corrige and em_teste(db, esc) and emissoes_do_escritorio(db, esc) >= config().teste_max_emissoes:
        from app.core.escritorios import CONTRATE
        raise ErroEmissao(f"O teste grátis permite emitir {config().teste_max_emissoes} nota, e ela já foi usada. "
                          f"{CONTRATE}", 402)
    e, cfg = _empresa_pronta(db, esc, ent.empresa_id)
    amb = ambiente(cfg)
    nota = NotaEmitida(escritorio_id=esc, empresa_id=e.id, usuario_id=usuario_id, ambiente=amb, serie=cfg.serie,
                       numero=0, id_dps="", situacao="enviando", recorrente_id=ent.recorrente_id, canal=canal(cfg))
    _preencher(db, nota, e, cfg, ent)
    if ent.substituicao:
        nota.subst_chave, _ = _substituida(db, esc, e, amb, ent.substituicao)
        nota.subst_motivo = ent.substituicao.get("motivo")
        nota.subst_justificativa = " ".join((ent.substituicao.get("justificativa") or "").split())
    # Valida tudo (regras e XSD) antes de gastar um número
    try:
        nota.numero = cfg.proximo_numero if nota.canal == NACIONAL else 1
        _xml_assinado(db, e, cfg, nota)
    except DpsInvalida as ex:
        db.rollback()
        raise ErroEmissao(str(ex)) from None

    if nota.canal == ISSNET_DF:
        with _trava(e.id):
            try:
                _reservar_rps(db, e, cfg, amb, nota)
            except ErroEmissao:
                db.rollback()
                raise
            if ent.salvar_tomador:
                _salvar_tomador(db, esc, ent.tomador)
            db.commit()  # RPS reservado antes de enviar
        xml = _xml_assinado(db, e, cfg, nota)
        nota.xml_dps_path = _gravar(e, amb, f"{nota.id_dps}.xml", xml)
        _enviar_issnet(db, e, cfg, nota, xml)
        db.commit()
        return nota

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
    _enviar(db, e, nota, xml, cfg)
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
    if nota.situacao == "pendente" and nota.canal == ISSNET_DF:
        with _cliente_issnet(db, e, nota.ambiente) as cli:
            resultado = _recuperar_issnet(cli, db, e, cfg, nota, motivo="Conferência antes do reenvio.")
        if resultado != "nao_gerada":
            db.commit()
            return nota
    elif nota.situacao == "pendente":
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
    if nota.canal == ISSNET_DF:
        _enviar_issnet(db, e, cfg, nota, xml)
    else:
        _enviar(db, e, nota, xml, cfg)
    db.commit()
    return nota


def cancelar(db: Session, esc: int, nota_id: int, motivo: str, justificativa: str) -> NotaEmitida:
    nota = _nota(db, esc, nota_id)
    if nota.situacao != "autorizada" or not nota.chave:
        raise ErroEmissao("Só dá para cancelar uma nota autorizada.", 409)
    from app.api.emissor import certificado_emissor, certificado_proprio
    e = db.get(Empresa, nota.empresa_id)
    if nota.canal == ISSNET_DF:  # no ISSNet a procuração também cancela (testado em 15/11/2026)
        return _cancelar_issnet(db, e, nota, certificado_emissor(db, e), motivo, justificativa)
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
        validar_xsd(raiz, nota.ambiente, "pedRegEvento_v1.01.xsd")  # igual nos dois leiautes
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


# Eventos consultados na Sefin (leitura): cancelamento comum, por substituição e por ofício
EVENTOS_CANCELAMENTO = ("101101", "105102", "305101")


def verificar_situacao(db: Session, esc: int, nota_id: int) -> tuple[NotaEmitida, str]:
    """Confere se a nota autorizada foi cancelada fora do Contask: primeiro pelos eventos do ADN já
    baixados, depois consultando a Sefin Nacional (só leitura). Devolve a nota e uma mensagem."""
    from app.api.emissor import certificado_emissor
    from app.emissor.situacao import conciliar_com_adn, dados_do_evento, marcar_cancelada, motivo_do_evento
    nota = _nota(db, esc, nota_id)
    if nota.situacao != "autorizada" or not nota.chave:
        return nota, "Só as notas autorizadas são conferidas."
    if conciliar_com_adn(db, nota.empresa_id, {nota.chave}):
        db.commit()
        return nota, "A nota foi cancelada fora do Contask (evento do ADN). A situação foi atualizada."
    e = db.get(Empresa, nota.empresa_id)
    cert = certificado_emissor(db, e)
    if cert is None:
        raise ErroEmissao("Cadastre o certificado da empresa (ou a procuração) para consultar a Sefin.", 409)
    pfx, senha = carregar_pfx(cert)
    with fabrica_cliente(nota.ambiente, pfx, senha) as cli:
        for tipo in EVENTOS_CANCELAMENTO:
            try:
                xml = cli.consultar_evento(nota.chave, tipo)
            except ErroSefin as ex:
                raise ErroEmissao(f"Não foi possível consultar a Sefin: {ex}", 502) from None
            if xml is None:
                continue
            codigo, data = dados_do_evento(xml)
            rel = _gravar(e, nota.ambiente, f"EVT_{nota.chave}_{codigo or tipo}.xml", xml)
            marcar_cancelada(nota, codigo or tipo, data, rel, motivo_do_evento(xml))
            db.commit()
            return nota, "A nota foi cancelada fora do Contask. A situação foi atualizada."
    return nota, "Nenhum cancelamento registrado para esta nota. Ela continua autorizada."


def _cancelar_issnet(db: Session, e: Empresa, nota: NotaEmitida, cert, motivo: str, justificativa: str) -> NotaEmitida:
    if cert is None:
        raise ErroEmissao("Cadastre o certificado A1 da empresa ou use a procuração para cancelar pelo ISSNet.", 409)
    try:
        raiz = montar_cancelamento(Cancelamento(ambiente=nota.ambiente, cnpj_autor=e.cnpj, chave=nota.chave,
                                                motivo=motivo, justificativa=justificativa))
        pfx, senha = carregar_pfx(cert)
        chave, c = assinatura.carregar_chave(pfx, senha)
        assinatura.assinar(raiz, raiz[0], chave, c, perfil=PERFIS_ISSNET[0])
        envio = issnet_msg.cancelar_nfse(raiz)
        validar_xsd_issnet(etree.fromstring(envio.encode("utf-8")))
    except DpsInvalida as ex:
        raise ErroEmissao(str(ex)) from None

    def assinar_no_envelope(pedido_envio) -> None:  # mesma regra da DPS (ver _assinador_no_envelope)
        ped = pedido_envio[0]
        for sig in ped.findall(f"{{{assinatura.DS}}}Signature"):
            ped.remove(sig)
        assinatura.assinar(ped, ped[0], chave, c, perfil=PERFIS_ISSNET[0])

    with fabrica_issnet(nota.ambiente, pfx, senha) as cli:
        try:
            r = cli.chamar("CancelarNfse", envio, assinar=assinar_no_envelope)
        except ErroIssnet as ex:
            raise ErroEmissao(f"{ex} Confira a nota antes de tentar de novo.", 502) from None
    evs = issnet_msg.eventos(r)
    if not r.ok or not evs:
        raise ErroEmissao("O ISSNet recusou o cancelamento: " +
                          (issnet_msg.texto_erros(r.erros) or "sem evento na resposta."))
    nota.xml_cancelamento_path = _gravar(e, nota.ambiente, f"EVT_{nota.chave}_101101.xml", evs[0])
    nota.situacao, nota.cancelado_em = "cancelada", agora()
    nota.motivo_cancelamento = " ".join(justificativa.split())
    db.commit()
    return nota
