"""Gera backend/app/emissor/tabelas_ibscbs.json: as listas de cIndOp e cClassTrib que valem para a NFS-e.

    python -m app.tools.tabelas_ibscbs ANEXO_VII.xlsx CCLASSTRIB.json

- Anexo VII (cIndOp, tabela de indicadores da operação, NT 009), coluna indNFSe = "S":
  https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc
- cClassTrib: tabela oficial publicada no Portal da Conformidade Fácil
  (https://dfe-portal.svrs.rs.gov.br/DFE/ClassificacaoTributaria). A página traz os dados em
  `dadosOriginais`; exporte só os vigentes com IndNfse, no console do navegador:
      copy(JSON.stringify(dadosOriginais.flatMap(p => p.ClassificacoesTributarias
        .filter(c => c.IndNfse && !c.DthFimVig).map(c => [c.CodClassTrib, p.Cst, p.NomeCst,
        c.NomeReduzido || c.NomeClassTrib, c.PercRedIbs, c.PercRedCbs,
        (c.TexUrlLegislacao || "").replace(/.*#art/, "").trim()]))))
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

DESTINO = Path(__file__).resolve().parents[1] / "emissor" / "tabelas_ibscbs.json"


def _txt(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def ler_anexo_vii(caminho: Path) -> list[dict]:
    ws = openpyxl.load_workbook(caminho, read_only=True).worksheets[0]
    saida = []
    for linha in list(ws.iter_rows(values_only=True))[1:]:
        c = (list(linha) + [None] * 10)[:10]
        codigo = re.sub(r"\D", "", str(c[0] or ""))
        if len(codigo) != 6 or _txt(c[7]).upper() != "S":  # só os que valem para a NFS-e
            continue
        saida.append({"codigo": codigo, "tipo": _txt(c[1]), "caracteristica": _txt(c[2]),
                      "local": _txt(c[3]), "incidencia": _txt(c[9])})
    return saida


def ler_cclasstrib(caminho: Path) -> list[dict]:
    saida = []
    for cod, cst, nome_cst, nome, red_ibs, red_cbs, art in json.loads(caminho.read_text(encoding="utf-8")):
        nome = _txt(nome).replace("CBS.realizadas", "CBS, realizadas")
        saida.append({"codigo": cod, "cst": cst, "nome_cst": _txt(nome_cst), "nome": nome,
                      "red_ibs": red_ibs, "red_cbs": red_cbs, "lei": f"LC 214/2025, art. {art}" if art else None})
    return sorted(saida, key=lambda x: x["codigo"])


def main(argv=None) -> None:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        sys.exit(__doc__)
    dados = {"fontes": [Path(argv[0]).name, "Portal da Conformidade Fácil (SVRS), cClassTrib com IndNfse"],
             "cindop": ler_anexo_vii(Path(argv[0])), "cclasstrib": ler_cclasstrib(Path(argv[1]))}
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{DESTINO}: {len(dados['cindop'])} cIndOp e {len(dados['cclasstrib'])} cClassTrib.")


if __name__ == "__main__":
    main()
