"""Tabelas oficiais da NFS-e (Anexo B e Anexo VIII), geradas por app.tools.tabelas_nfse."""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).with_name("tabelas.json")


@lru_cache
def _dados() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return t.lower()


def _digitos(t: str) -> str:
    return "".join(c for c in (t or "") if c.isdigit())


def item_do_codigo(ctribnac: str) -> str:
    """171901 -> 17.19"""
    return f"{ctribnac[:2]}.{ctribnac[2:4]}"


def formatar_ctribnac(c: str) -> str:
    """171901 -> 17.19.01"""
    return f"{c[:2]}.{c[2:4]}.{c[4:6]}" if len(c) == 6 else c


def formatar_nbs(c: str) -> str:
    """113022100 -> 1.1302.21.00"""
    return f"{c[0]}.{c[1:5]}.{c[5:7]}.{c[7:9]}" if len(c) == 9 else c


def servico(codigo: str) -> dict | None:
    return next((s for s in _dados()["servicos"] if s["codigo"] == codigo), None)


def nbs_descricao(codigo: str) -> str | None:
    return _dados()["nbs"].get(codigo)


def buscar_servicos(q: str, limite: int = 30) -> list[dict]:
    termo, dig = _norm(q).strip(), _digitos(q)
    itens = _dados()["servicos"]
    if termo:
        palavras = termo.split()
        itens = [s for s in itens
                 if (dig and s["codigo"].startswith(dig)) or all(p in _norm(s["descricao"]) for p in palavras)]
    return [{**s, "codigo_formatado": formatar_ctribnac(s["codigo"])} for s in itens[:limite]]


def buscar_nbs(q: str, limite: int = 30) -> list[dict]:
    termo, dig = _norm(q).strip(), _digitos(q)
    saida = []
    for cod, desc in _dados()["nbs"].items():
        if not termo or (dig and cod.startswith(dig)) or all(p in _norm(desc) for p in termo.split()):
            saida.append({"codigo": cod, "codigo_formatado": formatar_nbs(cod), "descricao": desc})
            if len(saida) >= limite:
                break
    return saida


def sugestoes(ctribnac: str) -> list[dict]:
    """NBS, cIndOp e cClassTrib que o Anexo VIII relaciona ao item do código de tributação nacional."""
    lista = _dados()["correlacao"].get(item_do_codigo(ctribnac), [])
    return [{**s, "nbs_formatado": formatar_nbs(s["nbs"]), "nbs_descricao": nbs_descricao(s["nbs"])} for s in lista]
