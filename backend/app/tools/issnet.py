"""Chamadas de LEITURA ao webservice do ISSNet do DF, para a fase de homologação. Só quem tem acesso ao servidor roda.

    python -m app.tools.issnet wsdl EMPRESA_ID [--producao]       # baixa o WSDL (confere namespace e parâmetros)
    python -m app.tools.issnet cadastro EMPRESA_ID [--producao]   # ConsultarDadosCadastrais (CNPJ + IM)
    python -m app.tools.issnet rps EMPRESA_ID [--producao]        # sincroniza e mostra os RPS disponíveis

Usa o certificado A1 da própria empresa. Nada aqui emite, cancela ou altera nota.
Sem --producao, vai para a homologação da Nota Control.
"""
from __future__ import annotations

import argparse
import sys

from lxml import etree

from app.core.certificados import carregar_pfx
from app.core.config import config
from app.core.db import nova_sessao
from app.core.migracao import migrar
from app.emissor.dps import PRODUCAO, RESTRITA
from app.emissor.issnet import mensagens, rps
from app.emissor.issnet.soap import ClienteIssnet, ErroIssnet
from app.models import Empresa


def _cliente(db, empresa_id: int, producao: bool):
    from app.api.emissor import certificado_proprio, config_prestador
    e = db.get(Empresa, empresa_id)
    if e is None:
        sys.exit(f"Empresa {empresa_id} não encontrada.")
    cfg = config_prestador(db, e)
    if not cfg.inscricao_municipal:
        sys.exit("Informe a inscrição municipal da empresa nos dados do prestador.")
    cert = certificado_proprio(db, e)
    if cert is None:
        sys.exit("O ISSNet exige o certificado A1 da própria empresa.")
    pfx, senha = carregar_pfx(cert)
    amb = PRODUCAO if producao else RESTRITA
    return e, cfg, amb, ClienteIssnet(ambiente=amb, pfx=pfx, senha=senha)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="app.tools.issnet")
    ap.add_argument("comando", choices=["wsdl", "cadastro", "rps"])
    ap.add_argument("empresa_id", type=int)
    ap.add_argument("--producao", action="store_true")
    a = ap.parse_args(argv)
    migrar()
    with nova_sessao() as db:
        e, cfg, amb, cli = _cliente(db, a.empresa_id, a.producao)
        with cli:
            try:
                if a.comando == "wsdl":
                    destino = config().dados_dir / f"issnet_wsdl_{'producao' if a.producao else 'homologacao'}.xml"
                    destino.write_bytes(cli.wsdl())
                    print(f"WSDL salvo em {destino}")
                elif a.comando == "cadastro":
                    r = cli.chamar("ConsultarDadosCadastrais",
                                   mensagens.consultar_dados_cadastrais(e.cnpj, cfg.inscricao_municipal))
                    print(mensagens.texto_erros(r.erros) if r.erros else
                          etree.tostring(r.xml, pretty_print=True, encoding="unicode"))
                else:
                    s = rps.sincronizar(db, e.id, e.cnpj, cfg.inscricao_municipal, amb, cli)
                    if s.erro:
                        sys.exit(s.erro)
                    res = rps.resumo(db, e.id, amb)
                    print(f"{res.disponiveis} RPS disponíveis; faixas: {res.faixas}; situação: {res.nivel}")
            except ErroIssnet as ex:
                sys.exit(str(ex))


if __name__ == "__main__":
    main()
