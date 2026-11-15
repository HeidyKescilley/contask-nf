"""Códigos de tributação municipal do DF (cTribMun) e a correlação com o código nacional (cTribNac).

Fonte: planilha "Correlação Tributação Municipal x Tributação Nacional" da área de Downloads do ISSNet DF.
O ISSNet também aceita os códigos das atividades do cadastro da empresa (ConsultarDadosCadastrais), que podem
não estar aqui; por isso o cadastro do serviço aceita qualquer código de até 10 dígitos.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).with_name("ctribmun_df.json")


@lru_cache
def _itens() -> list[dict]:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))["itens"]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return t.lower()


def item(codigo: str) -> dict | None:
    c = str(int(codigo)) if (codigo or "").isdigit() else ""
    return next((i for i in _itens() if i["codigo"] == c), None)


def buscar(q: str = "", ctribnac: str | None = None, limite: int = 40) -> list[dict]:
    """Primeiro os códigos ligados ao cTribNac do serviço; o texto filtra por código ou descrição."""
    termo = _norm(q).strip()
    digitos = "".join(ch for ch in termo if ch.isdigit())
    saida = []
    for i in _itens():
        if ctribnac and ctribnac not in i["ctribnac"]:
            continue
        if termo and not (termo in _norm(i["descricao"]) or (digitos and i["codigo"].startswith(digitos))):
            continue
        saida.append(i)
        if len(saida) >= limite:
            break
    return saida
