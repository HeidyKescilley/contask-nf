"""Acesso ao gerenciador da fila (criado no lifespan da aplicação)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fila import Gerenciador

_gerenciador: "Gerenciador | None" = None


def definir_gerenciador(g: "Gerenciador | None") -> None:
    global _gerenciador
    _gerenciador = g


def gerenciador() -> "Gerenciador | None":
    return _gerenciador


def acordar_fila() -> None:
    if _gerenciador is not None:
        _gerenciador.acordar()


_exportador = None


def definir_exportador(x) -> None:
    global _exportador
    _exportador = x


def exportador_ativo():
    return _exportador
