"""Textos legais das informações complementares e variáveis de data das notas recorrentes.

O xInfComp não aceita quebra de linha (padrão TSString da Sefin), então os textos vão separados por espaço.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

TEXTO_SIMPLES = ('I - "DOCUMENTO EMITIDO POR ME OU EPP OPTANTE PELO SIMPLES NACIONAL"; e '
                 'II - "NÃO GERA DIREITO A CRÉDITO FISCAL DE IPI."')
TEXTO_PROCON = "PROCON: TEL 151- SETOR COMERCIAL SUL, QUADRA 8, BLOCO B-60, SALA 240- BRASILIA - DF"
LIMITE_INFO = 2000


def _limpar(v: str | None) -> str:
    return " ".join((v or "").split())


def compor(info: str | None, simples: bool, procon: bool) -> str | None:
    """Texto do usuário + Simples + PROCON, numa linha só."""
    partes = [p for p in (_limpar(info), TEXTO_SIMPLES if simples else "", TEXTO_PROCON if procon else "") if p]
    texto = " ".join(partes)
    if len(texto) > LIMITE_INFO:
        raise ValueError(f"As informações complementares, com os textos legais, passam de {LIMITE_INFO} caracteres.")
    return texto or None


def separar(info: str | None) -> tuple[str, bool, bool]:
    """Inverso de compor: (texto do usuário, tinha Simples, tinha PROCON). Usado ao duplicar ou corrigir."""
    texto = _limpar(info)
    tem_simples = TEXTO_SIMPLES in texto
    tem_procon = TEXTO_PROCON in texto
    for t in (TEXTO_SIMPLES, TEXTO_PROCON):
        texto = texto.replace(t, " ")
    return _limpar(texto), tem_simples, tem_procon


# ---------------------------------------------------------------------------
# Variáveis das notas recorrentes
# ---------------------------------------------------------------------------

def _mes_anterior(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def _ultimo(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


VARIAVEIS: dict[str, str] = {
    "mes_atual": "Mês da emissão (MM/AAAA)",
    "mes_anterior": "Mês anterior à emissão (MM/AAAA)",
    "primeiro_dia_mes_atual": "Primeiro dia do mês da emissão",
    "ultimo_dia_mes_atual": "Último dia do mês da emissão",
    "primeiro_dia_mes_anterior": "Primeiro dia do mês anterior",
    "ultimo_dia_mes_anterior": "Último dia do mês anterior",
}

_RE = re.compile(r"\{([^{}]*)\}")


def valores(emissao: date) -> dict[str, str]:
    atual = emissao.replace(day=1)
    ant = _mes_anterior(emissao)
    f = lambda d: d.strftime("%d/%m/%Y")  # noqa: E731
    return {
        "mes_atual": atual.strftime("%m/%Y"), "mes_anterior": ant.strftime("%m/%Y"),
        "primeiro_dia_mes_atual": f(atual), "ultimo_dia_mes_atual": f(_ultimo(atual)),
        "primeiro_dia_mes_anterior": f(ant), "ultimo_dia_mes_anterior": f(_ultimo(ant)),
    }


def desconhecidas(texto: str | None) -> list[str]:
    return sorted({m.strip() for m in _RE.findall(texto or "") if m.strip() not in VARIAVEIS})


def aplicar(texto: str | None, emissao: date) -> str:
    v = valores(emissao)
    return _RE.sub(lambda m: v.get(m.group(1).strip(), m.group(0)), texto or "")


def dia_no_mes(ano: int, mes: int, dia: int) -> date:
    """Dia escolhido no mês; em meses mais curtos, o último dia (31 em fevereiro = 28/29)."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def proxima_data(dia: int, depois_de: date, incluir: bool = True) -> date:
    """Próxima ocorrência do dia a partir de depois_de (incluindo ou não o próprio dia)."""
    d = dia_no_mes(depois_de.year, depois_de.month, dia)
    if d > depois_de or (incluir and d == depois_de):
        return d
    ano, mes = (depois_de.year + 1, 1) if depois_de.month == 12 else (depois_de.year, depois_de.month + 1)
    return dia_no_mes(ano, mes, dia)
