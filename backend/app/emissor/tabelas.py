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


# --- IBS/CBS: cIndOp (Anexo VII) e cClassTrib (Conformidade Fácil), gerados por app.tools.tabelas_ibscbs ---

ARQUIVO_IBSCBS = Path(__file__).with_name("tabelas_ibscbs.json")
# cClassTrib só de pessoa física (autônomo, nanoempreendedor): o prestador do Contask é sempre CNPJ
SO_PESSOA_FISICA = {"000006", "200055", "200056", "410015", "410035"}
INCIDENCIA_TOMADOR = "Endereço do Tomador/Adquirente"


@lru_cache
def _ibscbs() -> dict:
    return json.loads(ARQUIVO_IBSCBS.read_text(encoding="utf-8"))


def cindop(codigo: str | None) -> dict | None:
    return next((c for c in _ibscbs()["cindop"] if c["codigo"] == codigo), None)


def cclasstrib(codigo: str | None) -> dict | None:
    return next((c for c in _ibscbs()["cclasstrib"] if c["codigo"] == codigo), None)


def opcoes_ibscbs(ctribnac: str | None = None, cnbs: str | None = None) -> dict:
    """Listas de cIndOp e cClassTrib que valem para a NFS-e de uma empresa (CNPJ), com as sugeridas para o
    serviço primeiro: as que o Anexo VIII liga ao item (e, se informada, à NBS) vêm marcadas como sugeridas."""
    corr = _dados()["correlacao"].get(item_do_codigo(ctribnac), []) if ctribnac and len(ctribnac) == 6 else []
    da_nbs = [c for c in corr if c["nbs"] == cnbs] if cnbs else []
    ordem_ind = [c["cindop"] for c in da_nbs + corr if c.get("cindop")]
    ordem_cls = [c["cclasstrib"] for c in da_nbs + corr if c.get("cclasstrib")]

    def montar(lista: list[dict], ordem: list[str]) -> list[dict]:
        pos = {cod: i for i, cod in reversed(list(enumerate(ordem)))}
        saida = [{**x, "sugerido": x["codigo"] in pos} for x in lista]
        return sorted(saida, key=lambda x: (pos.get(x["codigo"], len(pos)), x["codigo"]))

    ind = [{**c, "exige_endereco_tomador": c["incidencia"] == INCIDENCIA_TOMADOR} for c in _ibscbs()["cindop"]]
    cls = [c for c in _ibscbs()["cclasstrib"] if c["codigo"] not in SO_PESSOA_FISICA]
    return {"cindop": montar(ind, ordem_ind), "cclasstrib": montar(cls, ordem_cls)}
