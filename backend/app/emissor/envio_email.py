"""Envio da NFS-e por e-mail (DANFSe em PDF + XML), pela caixa do sistema (notas@).

Vale para qualquer nota do escritório: as emitidas pelo Contask e as que chegaram pelo ADN (prestadas ou
tomadas). A nota recorrente pode pedir o envio automático: a nota nasce com `email_pendente` e o e-mail sai
assim que ela é autorizada (na hora da transmissão ou numa verificação seguinte).

Cuidados: no máximo LIMITE_DESTINATARIOS por envio e LIMITE_DIA envios por escritório em 24 horas (a caixa
é do sistema; não pode virar disparo em massa). O conteúdo do e-mail não vai para log.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import email as email_sistema
from app.core.config import config
from app.models import Empresa, Nota, NotaEmitida, NotaEnvio, NotaRecorrente, Usuario, agora

log = logging.getLogger("contask.envio_email")

LIMITE_DESTINATARIOS = 5
LIMITE_DIA = 200
TENTATIVAS_AUTOMATICAS = 3
_EMAIL = re.compile(r"^[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+$")


class ErroEnvio(Exception):
    """Mensagem pensada para o usuário."""

    def __init__(self, mensagem: str, status: int = 422):
        super().__init__(mensagem)
        self.status = status


@dataclass
class Pacote:
    escritorio_id: int
    empresa_id: int
    chave: str
    numero: str | None
    prestador: str
    tomador: str | None
    valor: Decimal | None
    emissao: datetime | None
    cancelada: bool
    xml: bytes
    pdf: bytes
    nota_id: int | None = None
    nota_emitida_id: int | None = None


def destinatarios(texto: str | list[str] | None) -> list[str]:
    """Separa por vírgula, ponto e vírgula ou espaço; valida e tira repetidos."""
    partes = texto if isinstance(texto, list) else re.split(r"[,;\s]+", texto or "")
    lista: list[str] = []
    for p in partes:
        p = (p or "").strip().lower()
        if not p:
            continue
        if len(p) > 200 or not _EMAIL.match(p):
            raise ErroEnvio(f"E-mail inválido: {p}")
        if p not in lista:
            lista.append(p)
    if not lista:
        raise ErroEnvio("Informe pelo menos um e-mail de destino.")
    if len(lista) > LIMITE_DESTINATARIOS:
        raise ErroEnvio(f"No máximo {LIMITE_DESTINATARIOS} destinatários por envio.")
    return lista


# --- montagem do pacote ---------------------------------------------------------------------------

def _ler(rel: str | None, faltando: str) -> bytes:
    if not rel or not (config().dados_dir / rel).is_file():
        raise ErroEnvio(faltando, 404)
    return (config().dados_dir / rel).read_bytes()


def pacote_adn(db: Session, n: Nota) -> Pacote:
    from fastapi import HTTPException
    from app.api.notas import pdf_da_nota
    e = db.get(Empresa, n.empresa_id)
    xml = _ler(n.xml_path, "O XML desta nota não está no servidor. Rode a busca de novo.")
    try:
        pdf = pdf_da_nota(db, n)
    except HTTPException as ex:
        raise ErroEnvio(str(ex.detail), ex.status_code) from None
    return Pacote(escritorio_id=e.escritorio_id, empresa_id=n.empresa_id, chave=n.chave, numero=n.numero,
                  prestador=n.emitente_nome or "-", tomador=n.tomador_nome, valor=n.valor_servico,
                  emissao=n.data_emissao, cancelada=n.status == "cancelada", xml=xml, pdf=pdf, nota_id=n.id)


def pacote_emitida(db: Session, n: NotaEmitida) -> Pacote:
    from app.fiscal import danfse_receita
    from app.fiscal.parser import XmlInvalido, parse_nfse
    if n.situacao not in ("autorizada", "cancelada") or not n.chave:
        raise ErroEnvio("Só dá para enviar nota autorizada.", 409)
    xml = _ler(n.xml_nfse_path, "O XML da nota autorizada não está no servidor.")
    cancelada = n.situacao == "cancelada"
    marca = ("SUBSTITUÍDA" if n.substituida_por_id else "CANCELADA") if cancelada else None
    try:
        pdf, _ = danfse_receita.gerar(xml, marca_dagua=marca)
        d = parse_nfse(xml)
    except XmlInvalido as ex:
        raise ErroEnvio(f"Não foi possível gerar o DANFSe: XML inválido ({ex}).") from None
    e = db.get(Empresa, n.empresa_id)
    return Pacote(escritorio_id=n.escritorio_id, empresa_id=n.empresa_id, chave=n.chave, numero=n.numero_nfse or d.numero,
                  prestador=d.emitente_nome or e.razao_social, tomador=d.tomador_nome or (n.tomador or {}).get("nome"),
                  valor=n.valor_servico, emissao=d.data_emissao, cancelada=cancelada, xml=xml, pdf=pdf,
                  nota_emitida_id=n.id)


def sugestao_adn(n: Nota) -> str | None:
    """Nota prestada: o e-mail do tomador que está no XML."""
    from app.fiscal.parser import email_tomador
    if n.papel != "prestada" or not n.xml_path or not (config().dados_dir / n.xml_path).is_file():
        return None
    return email_tomador((config().dados_dir / n.xml_path).read_bytes())


def sugestao_emitida(n: NotaEmitida) -> str | None:
    return ((n.tomador or {}).get("email") or "").strip() or None


# --- texto do e-mail -----------------------------------------------------------------------------

def _moeda(v: Decimal | None) -> str:
    if v is None:
        return "-"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto(p: Pacote, mensagem: str | None) -> tuple[str, str, str]:
    num = f"nº {p.numero}" if p.numero else ""
    assunto = f"NFS-e {num} {'cancelada ' if p.cancelada else ''}- {p.prestador}".replace("  ", " ")
    linhas = [
        ("Prestador", p.prestador),
        ("Tomador", p.tomador or "-"),
        ("Número", p.numero or "-"),
        ("Emissão", p.emissao.strftime("%d/%m/%Y") if p.emissao else "-"),
        ("Valor do serviço", _moeda(p.valor)),
        ("Chave de acesso", p.chave),
    ]
    abertura = (f"Segue a NFS-e {num} emitida por {p.prestador}" + (f" para {p.tomador}" if p.tomador else "") + ".")
    if p.cancelada:
        abertura += " Atenção: esta nota está CANCELADA."
    msg = (mensagem or "").strip()
    rodape = ("Em anexo: o DANFSe (PDF) e o XML da nota. A autenticidade pode ser conferida pela chave de acesso "
              "na consulta pública do portal da NFS-e Nacional (nfse.gov.br).")
    texto = "\n".join(["Olá,", "", abertura, ""] + [f"{r}: {v}" for r, v in linhas]
                      + ([""] + [msg] if msg else []) + ["", rodape, "", "Enviado pelo Contask NF."])
    e = html.escape
    tabela = "".join(f'<tr><td style="padding:2px 12px 2px 0;color:#555">{e(r)}</td><td><b>{e(v)}</b></td></tr>'
                     for r, v in linhas)
    corpo_msg = f'<p style="white-space:pre-line">{e(msg)}</p>' if msg else ""
    html_ = (f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#111">'
             f"<p>Olá,</p><p>{e(abertura)}</p><table>{tabela}</table>{corpo_msg}"
             f'<p style="color:#555">{e(rodape)}</p><p style="color:#888;font-size:12px">Enviado pelo Contask NF.</p></div>')
    return assunto, texto, html_


# --- envio ---------------------------------------------------------------------------------------

def _enviados_24h(db: Session, esc: int) -> int:
    return int(db.scalar(select(func.count()).select_from(NotaEnvio).where(
        NotaEnvio.escritorio_id == esc, NotaEnvio.situacao == "enviado",
        NotaEnvio.criado_em >= agora() - timedelta(hours=24))) or 0)


def enviar(db: Session, p: Pacote, para: list[str], mensagem: str | None, usuario_id: int | None, *,
           recorrente_id: int | None = None, automatico: bool = False) -> NotaEnvio:
    """Envia e registra o resultado. Erro de e-mail fica registrado e sobe como ErroEnvio."""
    if not email_sistema.configurado():
        raise ErroEnvio("O e-mail do sistema ainda não está configurado no servidor. Fale com o suporte.", 503)
    if _enviados_24h(db, p.escritorio_id) >= LIMITE_DIA:
        raise ErroEnvio(f"Limite de {LIMITE_DIA} envios por e-mail em 24 horas atingido. Tente mais tarde.", 429)
    if mensagem and len(mensagem) > 2000:
        raise ErroEnvio("A mensagem pode ter no máximo 2.000 caracteres.")
    u = db.get(Usuario, usuario_id) if usuario_id else None
    assunto, texto, corpo_html = _texto(p, mensagem)
    nome = f"NFSe_{p.numero or ''}_{p.chave}".replace("__", "_")
    reg = NotaEnvio(escritorio_id=p.escritorio_id, empresa_id=p.empresa_id, chave=p.chave, nota_id=p.nota_id,
                    nota_emitida_id=p.nota_emitida_id, recorrente_id=recorrente_id, usuario_id=usuario_id,
                    para=", ".join(para), situacao="enviado", automatico=automatico, criado_em=agora())
    try:
        email_sistema.enviar(para, assunto, texto, corpo_html,
                             anexos=[(f"{nome}.pdf", p.pdf, "application/pdf"), (f"{nome}.xml", p.xml, "application/xml")],
                             responder_para=u.email if u is not None and u.escritorio_id else None)
    except email_sistema.ErroEmail as ex:
        reg.situacao, reg.erro = "erro", str(ex)
        db.add(reg)
        db.commit()
        raise ErroEnvio(str(ex), 502) from None
    db.add(reg)
    db.commit()
    return reg


def envio_out(r: NotaEnvio, nomes: dict[int, str] | None = None) -> dict:
    from datetime import timezone
    criado = r.criado_em if r.criado_em.tzinfo else r.criado_em.replace(tzinfo=timezone.utc)
    return {"id": r.id, "para": r.para, "situacao": r.situacao, "erro": r.erro, "automatico": r.automatico,
            "criado_em": criado, "por": (nomes or {}).get(r.usuario_id) if r.usuario_id else None}


def historico(db: Session, esc: int, empresa_id: int, chave: str) -> list[dict]:
    envios = list(db.scalars(select(NotaEnvio).where(NotaEnvio.escritorio_id == esc, NotaEnvio.empresa_id == empresa_id,
                                                     NotaEnvio.chave == chave)
                             .order_by(NotaEnvio.criado_em.desc(), NotaEnvio.id.desc()).limit(20)))
    ids = {r.usuario_id for r in envios if r.usuario_id}
    nomes = {u.id: u.nome or u.email for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids)))} if ids else {}
    return [envio_out(r, nomes) for r in envios]


# --- envio automático (nota recorrente) -------------------------------------------------------------

def preparar_automatico(rec: NotaRecorrente, nota: NotaEmitida) -> None:
    """Marca a nota da recorrência para envio assim que for autorizada."""
    if not rec.email_enviar:
        return
    para = (rec.email_para or "").strip() or sugestao_emitida(nota) or ""
    nota.email_pendente = {"para": para, "mensagem": rec.email_mensagem or "", "tentativas": 0}


def processar_pendentes(db: Session, ids: list[int] | None = None) -> int:
    """Envia os e-mails automáticos das notas já autorizadas. Devolve quantos saíram."""
    q = select(NotaEmitida).where(NotaEmitida.email_pendente.is_not(None))
    if ids is not None:
        q = q.where(NotaEmitida.id.in_(ids))
    enviados = 0
    for n in list(db.scalars(q)):
        pend = dict(n.email_pendente or {})
        if n.situacao in ("enviando", "pendente"):
            continue  # ainda sem resultado: espera a próxima verificação
        rec = db.get(NotaRecorrente, n.recorrente_id) if n.recorrente_id else None
        if n.situacao != "autorizada":
            n.email_pendente = None  # rejeitada ou cancelada: não envia
            db.commit()
            continue
        erro = None
        try:
            para = destinatarios(pend.get("para"))
            enviar(db, pacote_emitida(db, n), para, pend.get("mensagem"), n.usuario_id,
                   recorrente_id=n.recorrente_id, automatico=True)
            enviados += 1
        except ErroEnvio as ex:
            erro = str(ex)
        except Exception:  # noqa: BLE001
            log.exception("Falha inesperada no envio automático da nota %s", n.id)
            erro = "Falha inesperada no envio."
        n = db.get(NotaEmitida, n.id)
        if erro is None:
            n.email_pendente = None
        else:
            pend["tentativas"] = int(pend.get("tentativas") or 0) + 1
            # endereço errado não melhora tentando de novo; falha do servidor de e-mail tenta até 3 vezes
            definitivo = (pend["tentativas"] >= TENTATIVAS_AUTOMATICAS
                          or any(x in erro for x in ("destino", "destinatário", "inválido")))
            n.email_pendente = None if definitivo else pend
            if definitivo and rec is not None and rec.ultima_nota_id == n.id:
                rec.ultimo_erro = f"A nota foi emitida, mas o e-mail não foi enviado: {erro}"
        db.commit()
    return enviados
