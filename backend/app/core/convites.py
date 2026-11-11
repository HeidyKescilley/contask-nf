"""Convites de uso único para cadastrar um escritório no servidor da internet (CONTASK_CADASTRO=convite).

O código aparece uma única vez para quem o gerou; no banco fica só o SHA-256.
"""
from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Convite, agora

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sem 0/O, 1/I/L: fácil de ditar


def _hash(codigo: str) -> str:
    limpo = "".join(c for c in (codigo or "").upper() if c.isalnum())
    return hashlib.sha256(limpo.encode("ascii", "ignore")).hexdigest()


def gerar(db: Session, descricao: str) -> str:
    """16 caracteres em 4 grupos (cerca de 79 bits): inviável de adivinhar."""
    bruto = "".join(secrets.choice(ALFABETO) for _ in range(16))
    codigo = "-".join(bruto[i:i + 4] for i in range(0, 16, 4))
    db.add(Convite(codigo_hash=_hash(codigo), descricao=(descricao or "").strip()[:200] or "Convite"))
    db.flush()
    return codigo


def valido(db: Session, codigo: str) -> Convite | None:
    c = db.scalar(select(Convite).where(Convite.codigo_hash == _hash(codigo)))
    if c is None or c.usado_em is not None or c.revogado:
        return None
    return c


def marcar_usado(c: Convite, escritorio_id: int) -> None:
    c.usado_em, c.escritorio_id = agora(), escritorio_id
