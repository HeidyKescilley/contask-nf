"""POC do emissor: carrega o certificado da contabilidade do banco real (só leitura)."""
import os, sys, pathlib
RAIZ = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "backend"))
os.chdir(RAIZ)
from sqlalchemy import select
from app.core.db import nova_sessao
from app.core.certificados import carregar_pfx
from app.adn.cliente import ssl_context
from app.models import Certificado, Empresa
import httpx

RESTRITA = "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional"
ADN_RESTRITA = "https://adn.producaorestrita.nfse.gov.br"

def carregar():
    with nova_sessao() as db:
        c = db.scalar(select(Certificado))
        contab = db.scalar(select(Empresa).where(Empresa.is_contabilidade))
        pfx, senha = carregar_pfx(c)
        return pfx, senha, c.titular_doc, contab

def cliente(base=RESTRITA):
    pfx, senha, *_ = carregar()
    return httpx.Client(base_url=base, verify=ssl_context(pfx, senha), timeout=60,
                        headers={"User-Agent": "ContaskNF/0.1"})
