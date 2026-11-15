"""Assinatura XMLDSig envelopada da DPS e do pedido de evento.

Validado na Sefin Nacional (produção restrita, 09/11/2026): a canonicalização tem que ser a EXCLUSIVA
(xml-exc-c14n). Com a C14N inclusiva a Sefin devolve E0714 mesmo com a assinatura correta.

O ISSNet do DF (webservice Padrão Nacional da Nota Control, manual v1.01 seção 7.3.3) pede outro perfil:
C14N INCLUSIVA (REC-xml-c14n-20010315) com RSA-SHA1 e digest SHA1. Por isso o perfil é um parâmetro.
"""
from __future__ import annotations

import base64
import hashlib
import warnings
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"


@dataclass(frozen=True)
class Perfil:
    c14n: str
    metodo: str
    digest: str
    exclusiva: bool
    hash: type

    def canon(self, el) -> bytes:
        return etree.tostring(el, method="c14n", exclusive=self.exclusiva)

    def resumo(self, dados: bytes) -> str:
        h = hashlib.sha256 if self.hash is hashes.SHA256 else hashlib.sha1
        return base64.b64encode(h(dados).digest()).decode()


SEFIN = Perfil(EXC_C14N, RSA_SHA256, SHA256, True, hashes.SHA256)
ISSNET = Perfil(C14N, RSA_SHA1, SHA1, False, hashes.SHA1)


def carregar_chave(pfx: bytes, senha: str):
    """(chave privada, certificado) do .pfx. Nunca registre o retorno em log."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        chave, cert, _ = pkcs12.load_key_and_certificates(pfx, senha.encode("utf-8"))
    return chave, cert


def assinar(raiz, alvo, chave, cert, perfil: Perfil = SEFIN) -> None:
    """Acrescenta <Signature> como último filho de `raiz`, referenciando `alvo` pelo atributo Id."""
    digest = perfil.resumo(perfil.canon(alvo))
    sig = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    si = etree.SubElement(sig, f"{{{DS}}}SignedInfo")
    etree.SubElement(si, f"{{{DS}}}CanonicalizationMethod", Algorithm=perfil.c14n)
    etree.SubElement(si, f"{{{DS}}}SignatureMethod", Algorithm=perfil.metodo)
    ref = etree.SubElement(si, f"{{{DS}}}Reference", URI=f"#{alvo.get('Id')}")
    tr = etree.SubElement(ref, f"{{{DS}}}Transforms")
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm=ENVELOPED)
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm=perfil.c14n)
    etree.SubElement(ref, f"{{{DS}}}DigestMethod", Algorithm=perfil.digest)
    etree.SubElement(ref, f"{{{DS}}}DigestValue").text = digest
    valor = chave.sign(perfil.canon(si), padding.PKCS1v15(), perfil.hash())
    etree.SubElement(sig, f"{{{DS}}}SignatureValue").text = base64.b64encode(valor).decode()
    xd = etree.SubElement(etree.SubElement(sig, f"{{{DS}}}KeyInfo"), f"{{{DS}}}X509Data")
    etree.SubElement(xd, f"{{{DS}}}X509Certificate").text = base64.b64encode(
        cert.public_bytes(serialization.Encoding.DER)).decode()


def conferir(raiz, perfil: Perfil = SEFIN) -> bool:
    """Confere a assinatura com a chave pública do próprio XML (usado em testes)."""
    from cryptography import x509
    sig = raiz.find(f"{{{DS}}}Signature")
    si = sig.find(f"{{{DS}}}SignedInfo")
    ref = si.find(f".//{{{DS}}}Reference").get("URI")[1:]
    alvo = next(e for e in raiz.iter() if e.get("Id") == ref)
    # o digest é calculado sem a assinatura (transformação envelopada)
    copia = etree.fromstring(etree.tostring(raiz))
    copia.remove(copia.find(f"{{{DS}}}Signature"))
    alvo_copia = next(e for e in copia.iter() if e.get("Id") == ref)
    if perfil.resumo(perfil.canon(alvo_copia)) != si.find(f".//{{{DS}}}DigestValue").text:
        return False
    cert = x509.load_der_x509_certificate(base64.b64decode(sig.find(f".//{{{DS}}}X509Certificate").text))
    try:
        cert.public_key().verify(base64.b64decode(sig.find(f"{{{DS}}}SignatureValue").text), perfil.canon(si),
                                 padding.PKCS1v15(), perfil.hash())
    except Exception:  # noqa: BLE001
        return False
    return alvo is not None
