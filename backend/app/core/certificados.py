"""Leitura de .pfx (e-CNPJ e e-CPF, ICP-Brasil) e armazenamento cifrado.

Nada aqui registra senha em log ou devolve a senha. O .pfx vai para disco já cifrado (Fernet),
e a senha cifrada fica no banco.
"""
from __future__ import annotations

import hashlib
import os
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
from cryptography.x509.oid import ExtensionOID, NameOID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cripto
from app.core.config import config
from app.fiscal.documentos import cnpj_valido, cpf_valido
from app.models import Certificado

OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")         # CNPJ da pessoa jurídica (e-CNPJ)
OID_DADOS_PF = x509.ObjectIdentifier("2.16.76.1.3.1")     # nascimento (8) + CPF (11) + ...
OID_RESPONSAVEL = x509.ObjectIdentifier("2.16.76.1.3.2")  # nome do responsável (e-CNPJ)

TAMANHO_MAXIMO = 64 * 1024


class CertificadoInvalido(ValueError):
    """Mensagem sempre pensada para ser mostrada ao usuário."""


@dataclass
class InfoCertificado:
    titular_doc: str
    titular_nome: str
    tipo: str  # e-CNPJ | e-CPF
    validade: datetime
    inicio_validade: datetime
    thumbprint: str
    emissor: str
    responsavel: str | None

    @property
    def dias_restantes(self) -> int:
        return dias_restantes(self.validade)


def dias_restantes(validade: datetime) -> int:
    if validade.tzinfo is None:
        validade = validade.replace(tzinfo=timezone.utc)
    return (validade - datetime.now(timezone.utc)).days


def situacao_validade(validade: datetime | None) -> str:
    """ok | vence_30 | vence_15 | vence_7 | vencido | ausente (alertas de 30, 15 e 7 dias)."""
    if validade is None:
        return "ausente"
    d = dias_restantes(validade)
    if validade.replace(tzinfo=validade.tzinfo or timezone.utc) <= datetime.now(timezone.utc):
        return "vencido"
    if d < 7:
        return "vence_7"
    if d < 15:
        return "vence_15"
    if d < 30:
        return "vence_30"
    return "ok"


def _texto_othername(valor: bytes) -> str:
    """Valor DER de um otherName (OCTET/PRINTABLE/UTF8 STRING): devolve o conteúdo como texto."""
    if len(valor) >= 2 and valor[0] in (0x04, 0x0C, 0x13, 0x16) and valor[1] < 0x80:
        valor = valor[2:2 + valor[1]]
    return valor.decode("latin-1", "replace").strip()


def ler_pfx(pfx: bytes, senha: str) -> tuple[InfoCertificado, object, x509.Certificate]:
    if not pfx:
        raise CertificadoInvalido("Selecione o arquivo do certificado (.pfx ou .p12).")
    if len(pfx) > TAMANHO_MAXIMO:
        raise CertificadoInvalido("O arquivo é grande demais para um certificado A1 (.pfx).")
    if pfx[0] != 0x30:
        raise CertificadoInvalido("O arquivo não é um certificado .pfx/.p12 válido.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            chave, cert, _ = pkcs12.load_key_and_certificates(pfx, (senha or "").encode("utf-8"))
    except ValueError:
        raise CertificadoInvalido("Senha do certificado incorreta (ou arquivo .pfx corrompido).") from None
    if cert is None or chave is None:
        raise CertificadoInvalido("O arquivo não contém o certificado com a chave privada.")

    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = str(cn[0].value).strip() if cn else ""
    nome, doc_cn = (cn.rsplit(":", 1) + [""])[:2] if ":" in cn else (cn, "")
    doc_cn = re.sub(r"\D", "", doc_cn)

    cnpj = cpf = responsavel = None
    try:
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        for o in san.get_values_for_type(x509.OtherName):
            texto = _texto_othername(o.value)
            if o.type_id == OID_CNPJ:
                cnpj = re.sub(r"\D", "", texto)[:14]
            elif o.type_id == OID_DADOS_PF:
                digitos = re.sub(r"\D", "", texto)
                cpf = digitos[8:19] if len(digitos) >= 19 else None
            elif o.type_id == OID_RESPONSAVEL:
                responsavel = texto or None
    except x509.ExtensionNotFound:
        pass

    if cnpj and cnpj_valido(cnpj):
        tipo, doc = "e-CNPJ", cnpj
    elif len(doc_cn) == 14 and cnpj_valido(doc_cn):
        tipo, doc = "e-CNPJ", doc_cn
    elif cpf and cpf_valido(cpf):
        tipo, doc = "e-CPF", cpf
    elif len(doc_cn) == 11 and cpf_valido(doc_cn):
        tipo, doc = "e-CPF", doc_cn
    else:
        raise CertificadoInvalido("Não foi possível identificar o CNPJ ou CPF do titular. É um e-CNPJ ou e-CPF ICP-Brasil?")

    emissor = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    info = InfoCertificado(
        titular_doc=doc,
        titular_nome=nome.strip() or doc,
        tipo=tipo,
        validade=cert.not_valid_after_utc,
        inicio_validade=cert.not_valid_before_utc,
        thumbprint=hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest(),
        emissor=str(emissor[0].value) if emissor else "",
        responsavel=responsavel,
    )
    return info, chave, cert


def validar_para_uso(info: InfoCertificado) -> None:
    agora = datetime.now(timezone.utc)
    if info.validade <= agora:
        raise CertificadoInvalido(f"Certificado vencido em {info.validade:%d/%m/%Y}. Envie um certificado válido.")
    if info.inicio_validade > agora:
        raise CertificadoInvalido(f"Certificado só passa a valer em {info.inicio_validade:%d/%m/%Y}.")


def salvar_certificado(db: Session, pfx: bytes, senha: str, info: InfoCertificado, *, escritorio_id: int) -> Certificado:
    """Grava (ou atualiza, se o mesmo certificado já existe neste escritório) com .pfx e senha cifrados."""
    pasta = config().dados_dir / "certificados"
    pasta.mkdir(parents=True, exist_ok=True)

    cert = db.scalar(select(Certificado).where(Certificado.escritorio_id == escritorio_id,
                                               Certificado.thumbprint == info.thumbprint))
    if cert is None:
        cert = Certificado(escritorio_id=escritorio_id, thumbprint=info.thumbprint, pfx_cifrado_path="", senha_cifrada="")
        db.add(cert)
    cert.titular_doc, cert.titular_nome, cert.tipo, cert.validade = (
        info.titular_doc, info.titular_nome, info.tipo, info.validade)
    cert.senha_cifrada = cripto.cifrar_texto(senha)
    db.flush()  # garante o id

    destino = pasta / f"{cert.id}.pfx.enc"
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(cripto.cifrar(pfx))
    os.replace(tmp, destino)
    cert.pfx_cifrado_path = str(destino.relative_to(config().dados_dir).as_posix())
    return cert


def carregar_pfx(cert: Certificado) -> tuple[bytes, str]:
    """Para o cliente mTLS. Nunca registre o retorno em log."""
    caminho = config().dados_dir / cert.pfx_cifrado_path
    return cripto.decifrar(Path(caminho).read_bytes()), cripto.decifrar_texto(cert.senha_cifrada)


def remover_arquivo(cert: Certificado) -> None:
    caminho = config().dados_dir / cert.pfx_cifrado_path
    if cert.pfx_cifrado_path and caminho.is_file():
        caminho.unlink()
