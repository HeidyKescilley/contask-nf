"""Gera .pfx de teste no formato ICP-Brasil (CN "NOME:DOC" + otherNames no SAN)."""
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID

_CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _octet(texto: str) -> bytes:
    b = texto.encode("latin-1")
    return bytes([0x04, len(b)]) + b


def dv_cnpj(base12: str) -> str:
    def dv(s, pesos):
        r = sum((ord(c) - 48) * p for c, p in zip(s, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])


def criar_pfx(nome: str, *, cnpj: str | None = None, cpf: str | None = None, dias: int = 365,
              senha: str = "S3nh@-Teste!", inicio_dias: int = -10) -> bytes:
    agora = datetime.now(timezone.utc)
    doc = cnpj or cpf
    sujeito = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{nome}:{doc}")])
    emissor = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AC Teste Contask")])
    outros = []
    if cnpj:
        outros.append(x509.OtherName(x509.ObjectIdentifier("2.16.76.1.3.3"), _octet(cnpj)))
        outros.append(x509.OtherName(x509.ObjectIdentifier("2.16.76.1.3.2"), _octet("RESPONSAVEL TESTE")))
    if cpf:
        outros.append(x509.OtherName(x509.ObjectIdentifier("2.16.76.1.3.1"), _octet("01011980" + cpf + "0" * 15)))
    cert = (
        x509.CertificateBuilder()
        .subject_name(sujeito).issuer_name(emissor).public_key(_CHAVE.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora + timedelta(days=inicio_dias))
        .not_valid_after(agora + timedelta(days=dias))
        .add_extension(x509.SubjectAlternativeName(outros), critical=False)
        .sign(_CHAVE, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(b"teste", _CHAVE, cert, None,
                                                 BestAvailableEncryption(senha.encode()))
