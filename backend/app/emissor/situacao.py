"""Situação das notas emitidas pelo Contask a partir dos eventos de fora (portal nacional, prefeitura, ofício).

A nota pode ser cancelada fora do Contask (Emissor Nacional Web, por exemplo). O status vem só dos
eventos: os do ADN (busca por NSU, que já recalcula a `Nota`) e, sob pedido, os consultados na Sefin.
"""
from __future__ import annotations

from datetime import datetime

from lxml import etree
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.fiscal.parser import N, XmlInvalido, parse_evento
from app.fiscal.status import CANCELAMENTOS, DESCRICOES
from app.models import DocumentoDfe, EventoNota, Nota, NotaEmitida, agora

PRODUCAO = 1


def motivo_do_evento(xml: bytes | None) -> str | None:
    if not xml:
        return None
    try:
        raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return None
    el = raiz.find(".//n:xMotivo", N)
    return " ".join(el.text.split()) if el is not None and el.text else None


def marcar_cancelada(nota: NotaEmitida, codigo: str, data: datetime | None, xml_rel: str | None, motivo: str | None) -> None:
    nota.situacao = "cancelada"
    nota.cancelado_em = data or agora()
    nota.xml_cancelamento_path = nota.xml_cancelamento_path or xml_rel
    origem = CANCELAMENTOS.get(codigo) or DESCRICOES.get(codigo) or "Cancelamento"
    nota.motivo_cancelamento = motivo or f"{origem} registrado fora do Contask."
    nota.mensagem = f"{origem} registrado fora do Contask (evento {codigo})."


def conciliar_com_adn(db: Session, empresa_id: int | None = None, chaves: set[str] | None = None) -> int:
    """Nota emitida ainda autorizada cuja NFS-e no ADN está cancelada pelos eventos passa a cancelada."""
    stmt = (select(NotaEmitida, Nota)
            .join(Nota, and_(Nota.chave == NotaEmitida.chave, Nota.empresa_id == NotaEmitida.empresa_id))
            .where(NotaEmitida.situacao == "autorizada", NotaEmitida.ambiente == PRODUCAO, Nota.status == "cancelada"))
    if empresa_id is not None:
        stmt = stmt.where(NotaEmitida.empresa_id == empresa_id)
    if chaves is not None:
        if not chaves:
            return 0
        stmt = stmt.where(NotaEmitida.chave.in_(chaves))
    mudou = 0
    for emitida, nota in db.execute(stmt).all():
        ev = db.scalars(select(EventoNota).where(EventoNota.empresa_id == nota.empresa_id, EventoNota.chave == nota.chave,
                                                 EventoNota.codigo.in_(CANCELAMENTOS))
                        .order_by(EventoNota.data_evento, EventoNota.nsu)).first()
        if ev is None:
            continue
        doc = db.get(DocumentoDfe, ev.documento_id) if ev.documento_id else None
        xml = None
        if doc and doc.xml_path:
            arq = config().dados_dir / doc.xml_path
            xml = arq.read_bytes() if arq.is_file() else None
        marcar_cancelada(emitida, ev.codigo, ev.data_evento, doc.xml_path if doc else None, motivo_do_evento(xml))
        mudou += 1
    return mudou


def dados_do_evento(xml: bytes) -> tuple[str | None, datetime | None]:
    try:
        ev = parse_evento(xml)
    except (XmlInvalido, etree.XMLSyntaxError, AttributeError):
        return None, None
    return ev.codigo, ev.data_evento
