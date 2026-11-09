"""Assinatura XMLDSig envelopada da DPS e do pedido de evento.

Validado na Sefin Nacional (produção restrita, 09/11/2026): a canonicalização tem que ser a EXCLUSIVA
(xml-exc-c14n). Com a C14N inclusiva a Sefin devolve E0714 mesmo com a assinatura correta.
"""
from __future__ import annotations

import base64
import hashlib
import warnings

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"


def carregar_chave(pfx: bytes, senha: str):
    """(chave privada, certificado) do .pfx. Nunca registre o retorno em log."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        chave, cert, _ = pkcs12.load_key_and_certificates(pfx, senha.encode("utf-8"))
    return chave, cert


def _c14n(el) -> bytes:
    return etree.tostring(el, method="c14n", exclusive=True)


def assinar(raiz, alvo, chave, cert) -> None:
    """Acrescenta <Signature> como último filho de `raiz`, referenciando `alvo` pelo atributo Id."""
    digest = base64.b64encode(hashlib.sha256(_c14n(alvo)).digest()).decode()
    sig = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    si = etree.SubElement(sig, f"{{{DS}}}SignedInfo")
    etree.SubElement(si, f"{{{DS}}}CanonicalizationMethod", Algorithm=EXC_C14N)
    etree.SubElement(si, f"{{{DS}}}SignatureMethod", Algorithm=RSA_SHA256)
    ref = etree.SubElement(si, f"{{{DS}}}Reference", URI=f"#{alvo.get('Id')}")
    tr = etree.SubElement(ref, f"{{{DS}}}Transforms")
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm=ENVELOPED)
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm=EXC_C14N)
    etree.SubElement(ref, f"{{{DS}}}DigestMethod", Algorithm=SHA256)
    etree.SubElement(ref, f"{{{DS}}}DigestValue").text = digest
    valor = chave.sign(_c14n(si), padding.PKCS1v15(), hashes.SHA256())
    etree.SubElement(sig, f"{{{DS}}}SignatureValue").text = base64.b64encode(valor).decode()
    xd = etree.SubElement(etree.SubElement(sig, f"{{{DS}}}KeyInfo"), f"{{{DS}}}X509Data")
    etree.SubElement(xd, f"{{{DS}}}X509Certificate").text = base64.b64encode(
        cert.public_bytes(serialization.Encoding.DER)).decode()


def conferir(raiz) -> bool:
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
    if base64.b64encode(hashlib.sha256(_c14n(alvo_copia)).digest()).decode() != si.find(f".//{{{DS}}}DigestValue").text:
        return False
    cert = x509.load_der_x509_certificate(base64.b64decode(sig.find(f".//{{{DS}}}X509Certificate").text))
    try:
        cert.public_key().verify(base64.b64decode(sig.find(f"{{{DS}}}SignatureValue").text), _c14n(si),
                                 padding.PKCS1v15(), hashes.SHA256())
    except Exception:  # noqa: BLE001
        return False
    return alvo is not None
