"""Backup da pasta dados/ num ZIP, com cópia consistente do banco (API de backup do SQLite).

    .venv\\Scripts\\python -m app.tools.backup [--destino PASTA]

Inclui: banco, XMLs e eventos das empresas, certificados (cifrados), foto da migração.
Não inclui: PDFs (são gerados de novo a partir do XML) e exportações (podem ser geradas de novo).

ATENÇÃO: os certificados no backup estão cifrados com a chave-mestra guardada no Gerenciador de
Credenciais do Windows. Sem essa chave (ex.: Windows reinstalado), as notas continuam legíveis,
mas os certificados precisam ser enviados de novo pela tela.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.config import RAIZ, config

IGNORAR = {"pdf", "exportacoes"}


def fazer_backup(destino: Path | None = None) -> Path:
    dados = config().dados_dir
    destino = destino or (RAIZ / "backups")
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / f"contask_backup_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "contask.db"
        origem = sqlite3.connect(dados / "contask.db")
        alvo = sqlite3.connect(copia)
        with alvo:
            origem.backup(alvo)
        origem.close()
        alvo.close()
        with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, "dados/contask.db")
            for p in sorted(dados.rglob("*")):
                rel = p.relative_to(dados)
                if not p.is_file() or rel.parts[0] in IGNORAR or p.name.startswith("contask.db") or p.suffix == ".tmp":
                    continue
                if len(rel.parts) > 2 and rel.parts[0] == "empresas" and rel.parts[2] in IGNORAR:
                    continue
                z.write(p, f"dados/{rel.as_posix()}")
            z.writestr("LEIA-ME.txt", (
                "Backup do Contask NF.\n\nPara restaurar: feche o sistema, extraia a pasta 'dados' deste ZIP na pasta do "
                "Contask NF (substituindo a atual) e abra o iniciar.bat.\n\nOs certificados estão cifrados com a chave-mestra do "
                "Gerenciador de Credenciais do Windows (serviço 'ContaskNF'). Em outro computador ou após reinstalar o Windows, "
                "envie os certificados de novo pela tela: as notas continuam disponíveis.\n"))
    return arq


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backup da pasta dados/ do Contask NF.")
    ap.add_argument("--destino", type=Path)
    a = ap.parse_args(argv)
    arq = fazer_backup(a.destino)
    print(f"Backup criado: {arq} ({arq.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
