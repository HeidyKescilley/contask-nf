"""Gera backend/app/emissor/tabelas.json a partir das planilhas oficiais da NFS-e (dados públicos).

    python -m app.tools.tabelas_nfse ANEXO_B.xlsx ANEXO_VIII.xlsx

- Anexo B (Lista de serviço nacional + NBS 2.0):
  https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual
- Anexo VIII (correlação item LC 116 x NBS x cIndOp x cClassTrib):
  https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

DESTINO = Path(__file__).resolve().parents[1] / "emissor" / "tabelas.json"


def _txt(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def ler_anexo_b(caminho: Path) -> tuple[list[dict], dict[str, str]]:
    wb = openpyxl.load_workbook(caminho, read_only=True)
    servicos = []
    for linha in list(wb["LISTA.SERV.NAC."].iter_rows(values_only=True))[1:]:
        cod, item, sub, desd, desc = (list(linha) + [None] * 5)[:5]
        if desd in (None, "") or cod in (None, ""):
            continue  # só o desdobro tem código de 6 dígitos
        codigo = _digitos(cod).zfill(6)
        servicos.append({"codigo": codigo, "item": f"{int(item):02d}.{int(sub):02d}", "descricao": _txt(desc)})
    nbs = {}
    for linha in list(wb["LISTA.NBS_v2.0"].iter_rows(values_only=True))[1:]:
        cod, desc = (list(linha) + [None, None])[:2]
        d = _digitos(cod)
        if len(d) == 9:  # só o nível que vai na DPS (TSCodNBS = 9 dígitos)
            nbs[d] = _txt(desc)
    return servicos, nbs


def ler_anexo_viii(caminho: Path, nbs: dict[str, str]) -> dict[str, list[dict]]:
    ws = openpyxl.load_workbook(caminho, read_only=True)["tabela geral"]
    corr: dict[str, list[dict]] = {}
    item = indop = classtrib = None
    for linha in list(ws.iter_rows(values_only=True))[1:]:
        c = (list(linha) + [None] * 12)[:12]
        if c[0]:
            item, indop, classtrib = _txt(c[0]), None, None
        if not item:
            continue
        indop = _txt(c[6]) or indop  # células mescladas: vale a última informada no item
        classtrib = _txt(c[8]) or classtrib
        d = _digitos(c[2])
        if len(d) != 9:
            continue
        nbs.setdefault(d, _txt(c[3]))
        lista = corr.setdefault(item, [])
        if not any(x["nbs"] == d for x in lista):
            lista.append({"nbs": d, "cindop": indop if indop and len(_digitos(indop)) == 6 else None,
                          "cclasstrib": classtrib if classtrib and len(_digitos(classtrib)) == 6 else None})
    return corr


def main(argv=None) -> None:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        sys.exit(__doc__)
    servicos, nbs = ler_anexo_b(Path(argv[0]))
    corr = ler_anexo_viii(Path(argv[1]), nbs)
    dados = {"fontes": [Path(a).name for a in argv], "servicos": servicos,
             "nbs": dict(sorted(nbs.items())), "correlacao": corr}
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{DESTINO}: {len(servicos)} serviços, {len(nbs)} NBS, {len(corr)} itens com correlação.")


if __name__ == "__main__":
    main()
