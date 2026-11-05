"""Status da nota calculado só a partir dos eventos (Anexo II), em qualquer ordem de chegada.

Prioridade: Cancelada > Rejeitada > Autorizada. Código desconhecido não altera nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

CANCELAMENTOS = {
    "101101": None,
    "105102": "Cancelada por substituição",
    "105104": "Cancelamento deferido por análise fiscal",
    "305101": "Cancelada por ofício",
}
ANALISE = "101103"
ANALISE_FIM = {"105104", "105105"}  # deferido (cancela) ou indeferido (tira o selo)
REJEICOES = {"202205": "Rejeitada pelo prestador", "203206": "Rejeitada pelo tomador",
             "204207": "Rejeitada pelo intermediário"}
ANULA_REJEICAO = "205208"
BLOQUEIO, DESBLOQUEIO = "305102", "305103"
CONFIRMACOES = {"202201", "203202", "204203", "205204"}

DESCRICOES = {
    "101101": "Cancelamento", "105102": "Cancelamento por substituição",
    "101103": "Solicitação de análise fiscal para cancelamento",
    "105104": "Cancelamento deferido por análise fiscal", "105105": "Cancelamento indeferido por análise fiscal",
    "202201": "Confirmação do prestador", "203202": "Confirmação do tomador",
    "204203": "Confirmação do intermediário", "205204": "Confirmação tácita",
    "202205": "Rejeição do prestador", "203206": "Rejeição do tomador", "204207": "Rejeição do intermediário",
    "205208": "Anulação da rejeição", "305101": "Cancelamento por ofício",
    "305102": "Bloqueio por ofício", "305103": "Desbloqueio por ofício",
}
CONHECIDOS = set(DESCRICOES)


@dataclass(frozen=True)
class EventoStatus:
    codigo: str | None
    data: datetime | None
    nsu: int | None


@dataclass
class Status:
    status: str = "autorizada"  # autorizada|cancelada|rejeitada
    detalhe: str | None = None
    em_analise_fiscal: bool = False
    bloqueada: bool = False


_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _chave_ordem(e: EventoStatus):
    d = e.data or _MIN
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (d, e.nsu or 0)


def calcular_status(eventos: list[EventoStatus]) -> Status:
    ordem = sorted((e for e in eventos if e.codigo in CONHECIDOS), key=_chave_ordem)
    s = Status()
    rejeicao: str | None = None
    for e in ordem:
        c = e.codigo
        if c == ANALISE:
            s.em_analise_fiscal = True
        elif c in ANALISE_FIM:
            s.em_analise_fiscal = False
        if c in REJEICOES:
            rejeicao = REJEICOES[c]
        elif c == ANULA_REJEICAO:
            rejeicao = None
        if c == BLOQUEIO:
            s.bloqueada = True
        elif c == DESBLOQUEIO:
            s.bloqueada = False

    cancel = [e for e in ordem if e.codigo in CANCELAMENTOS]
    if cancel:
        s.status, s.detalhe, s.em_analise_fiscal = "cancelada", CANCELAMENTOS[cancel[0].codigo], False
    elif rejeicao:
        s.status, s.detalhe = "rejeitada", rejeicao
    return s
