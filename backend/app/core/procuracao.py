"""Certificados de procurador da contabilidade.

A contabilidade pode ter dois certificados de procurador: o principal (em geral o e-CNPJ do escritório) e
um segundo (em geral o e-CPF do contador). Cada empresa por procuração pode ter dado a procuração a só um
deles. A busca no ADN testa os dois e guarda em `Empresa.certificado_procurador_id` o que funcionou: ele
vira o padrão da empresa (busca e emissão), até falhar e o outro ser testado de novo.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.certificados import situacao_validade
from app.models import Certificado, Empresa


def contabilidade(db: Session, escritorio_id: int) -> Empresa | None:
    return db.scalar(select(Empresa).where(Empresa.escritorio_id == escritorio_id, Empresa.is_contabilidade))


def certificados_contabilidade(db: Session, escritorio_id: int) -> list[Certificado]:
    """Principal e segundo certificado da contabilidade, nessa ordem (sem repetir)."""
    c = contabilidade(db, escritorio_id)
    if c is None:
        return []
    saida: list[Certificado] = []
    for cid in (c.certificado_id, c.certificado_extra_id):
        cert = db.get(Certificado, cid) if cid else None
        if cert is not None and all(x.id != cert.id for x in saida):
            saida.append(cert)
    return saida


def por_procuracao(e: Empresa) -> bool:
    return e.modo_certificado == "contabilidade" and not e.is_contabilidade


def candidatos(db: Session, e: Empresa) -> list[Certificado]:
    """Certificados a testar para a empresa por procuração: o padrão dela primeiro; vencidos por último."""
    if not por_procuracao(e):
        return []
    lista = certificados_contabilidade(db, e.escritorio_id)
    return sorted(lista, key=lambda c: (situacao_validade(c.validade) == "vencido", c.id != e.certificado_procurador_id))


def certificado_procurador(db: Session, e: Empresa) -> Certificado | None:
    """O certificado da contabilidade que vale para a empresa (o padrão dela ou, sem padrão, o principal)."""
    lista = candidatos(db, e)
    return lista[0] if lista else None


def definir_padrao(e: Empresa, cert: Certificado) -> bool:
    """Grava o certificado com procuração como padrão da empresa. Devolve True se mudou."""
    if e.certificado_procurador_id == cert.id:
        return False
    e.certificado_procurador_id = cert.id
    return True
