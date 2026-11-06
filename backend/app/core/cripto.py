"""Cifragem de segredos (pfx e senhas) com Fernet.

A chave-mestra vem só de CONTASK_CHAVE_MESTRA (Fernet, base64). Sem ela, ou com valor
inválido, a API não sobe. Certificado cifrado com outra chave não abre: as notas e os
XMLs continuam legíveis e o .pfx precisa ser enviado de novo.
"""
from __future__ import annotations

import threading

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import config

_lock = threading.Lock()
_fernet: Fernet | None = None


class ErroCripto(Exception):
    pass


def _carregar_chave() -> bytes:
    cfg = config()
    bruto = cfg.chave_mestra.get_secret_value().strip() if cfg.chave_mestra is not None else ""
    if not bruto:
        raise ErroCripto("Defina CONTASK_CHAVE_MESTRA (chave Fernet em base64) no ambiente ou no .env.")
    try:
        chave = bruto.encode("ascii")
        Fernet(chave)
    except Exception as e:
        raise ErroCripto("CONTASK_CHAVE_MESTRA inválida. Gere com Fernet.generate_key().") from e
    return chave


def _f() -> Fernet:
    global _fernet
    with _lock:
        if _fernet is None:
            _fernet = Fernet(_carregar_chave())
        return _fernet


def definir_chave_para_testes(chave: bytes | None) -> None:
    """Usado só em testes: injeta a chave sem ler o ambiente."""
    global _fernet
    with _lock:
        _fernet = Fernet(chave) if chave else None


def chave_disponivel() -> bool:
    try:
        _f()
        return True
    except Exception:
        return False


def cifrar(dados: bytes) -> bytes:
    return _f().encrypt(dados)


def decifrar(token: bytes) -> bytes:
    try:
        return _f().decrypt(token)
    except InvalidToken as e:
        raise ErroCripto("Não foi possível decifrar: chave-mestra diferente ou dado corrompido.") from e


def cifrar_texto(texto: str) -> str:
    return cifrar(texto.encode("utf-8")).decode("ascii")


def decifrar_texto(token: str) -> str:
    return decifrar(token.encode("ascii")).decode("utf-8")
