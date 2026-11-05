"""Cifragem de segredos (pfx e senhas) com Fernet.

Origem da chave-mestra, nesta ordem:
- CONTASK_CHAVE_MESTRA (valor direto, ex.: segredo do servidor);
- CONTASK_CHAVE_MESTRA_ARQUIVO (arquivo só do dono, criado na primeira abertura; servidor Linux);
- Gerenciador de Credenciais do Windows (keyring), no uso local.
Sem a chave, os certificados precisam ser reenviados; as notas continuam legíveis.
"""
from __future__ import annotations

import os
import threading

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import config

_USUARIO_KEYRING = "chave-mestra"
_lock = threading.Lock()
_fernet: Fernet | None = None


class ErroCripto(Exception):
    pass


def _chave_do_arquivo(caminho) -> bytes:
    if caminho.is_file():
        chave = caminho.read_text(encoding="ascii").strip()
        if not chave:
            raise ErroCripto(f"Arquivo da chave-mestra vazio: {caminho}")
        return chave.encode()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    chave = Fernet.generate_key()
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(chave + b"\n")
    return chave


def _carregar_ou_criar_chave() -> bytes:
    cfg = config()
    if cfg.chave_mestra is not None and cfg.chave_mestra.get_secret_value().strip():
        return cfg.chave_mestra.get_secret_value().strip().encode()
    if cfg.chave_mestra_arquivo is not None:
        return _chave_do_arquivo(cfg.chave_mestra_arquivo)
    import keyring  # só no uso local (Windows)

    servico = cfg.keyring_servico
    chave = keyring.get_password(servico, _USUARIO_KEYRING)
    if not chave:
        chave = Fernet.generate_key().decode()
        keyring.set_password(servico, _USUARIO_KEYRING, chave)
    return chave.encode()


def _f() -> Fernet:
    global _fernet
    with _lock:
        if _fernet is None:
            _fernet = Fernet(_carregar_ou_criar_chave())
        return _fernet


def definir_chave_para_testes(chave: bytes | None) -> None:
    """Usado só em testes: evita tocar no keyring real."""
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
