"""Login do servidor na internet: senha com scrypt, sessão em cookie HttpOnly.

- O banco guarda só o SHA-256 do token da sessão; o token vai apenas no cookie.
- Tentativas erradas por IP e por e-mail são limitadas (bloqueio temporário).
- Senha nunca vai para log nem para resposta da API.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import Escritorio, SessaoUsuario, Usuario

COOKIE = "contask_sessao"
SENHA_MINIMA = 10
_N, _R, _P = 2**14, 8, 1


class ErroLogin(Exception):
    """Mensagem sempre pensada para ser mostrada ao usuário."""


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _b64(x: bytes) -> str:
    return base64.b64encode(x).decode("ascii")


# --- senha --------------------------------------------------------------------

def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(h)}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        alg, n, r, p, sal, h = armazenado.split("$")
        if alg != "scrypt":
            return False
        esperado = base64.b64decode(h)
        calc = hashlib.scrypt(senha.encode("utf-8"), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p),
                              dklen=len(esperado))
        return hmac.compare_digest(calc, esperado)
    except (ValueError, TypeError):
        return False


_HASH_FALSO = gerar_hash(secrets.token_urlsafe(16))  # mesmo tempo de resposta para e-mail inexistente


def validar_nova_senha(senha: str) -> None:
    if len(senha or "") < SENHA_MINIMA:
        raise ErroLogin(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if senha.lower() == senha or senha.upper() == senha or not any(c.isdigit() for c in senha):
        raise ErroLogin("Use letras maiúsculas, minúsculas e pelo menos um número.")


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def senha_aleatoria() -> str:
    """Senha inicial que atende às regras (o usuário troca no primeiro acesso)."""
    while True:
        s = secrets.token_urlsafe(12)
        try:
            validar_nova_senha(s)
            return s
        except ErroLogin:
            continue


# --- limite de tentativas -----------------------------------------------------

class Limitador:
    """Até `maximo` erros em `janela` segundos por chave; depois, bloqueio até a janela passar."""

    def __init__(self, maximo: int = 5, janela: float = 15 * 60):
        self.maximo, self.janela = maximo, janela
        self._erros: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recentes(self, chave: str, t: float) -> list[float]:
        lst = [x for x in self._erros.get(chave, []) if t - x < self.janela]
        self._erros[chave] = lst
        return lst

    def bloqueado(self, *chaves: str) -> bool:
        t = time.monotonic()
        with self._lock:
            return any(len(self._recentes(c, t)) >= self.maximo for c in chaves)

    def falhou(self, *chaves: str) -> None:
        t = time.monotonic()
        with self._lock:
            for c in chaves:
                self._recentes(c, t).append(t)

    def limpar(self, *chaves: str) -> None:
        with self._lock:
            for c in chaves:
                self._erros.pop(c, None)


limitador = Limitador()


# --- sessões ------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def entrar(db: Session, email: str, senha: str, ip: str) -> tuple[Usuario, str]:
    email = normalizar_email(email)
    chaves = (f"ip:{ip}", f"email:{email}")
    if limitador.bloqueado(*chaves):
        raise ErroLogin("Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    ok = conferir_senha(senha or "", u.senha_hash if u else _HASH_FALSO)
    if not (u and ok and u.ativo):
        limitador.falhou(*chaves)
        raise ErroLogin("E-mail ou senha incorretos.")
    limitador.limpar(*chaves)
    token = secrets.token_urlsafe(32)
    db.execute(delete(SessaoUsuario).where(SessaoUsuario.expira_em < agora()))
    db.add(SessaoUsuario(token_hash=_hash_token(token), usuario_id=u.id, criado_em=agora(),
                         expira_em=agora() + timedelta(days=config().sessao_dias)))
    u.ultimo_acesso_em = agora()
    db.commit()
    return u, token


def usuario_da_sessao(db: Session, token: str | None) -> Usuario | None:
    if not token:
        return None
    s = db.get(SessaoUsuario, _hash_token(token))
    if s is None:
        return None
    exp = _utc(s.expira_em)
    if exp <= agora():
        db.delete(s)
        db.commit()
        return None
    u = db.get(Usuario, s.usuario_id)
    if u is None or not u.ativo:
        return None
    # Renova a sessão em uso (no máximo uma escrita por hora)
    novo = agora() + timedelta(days=config().sessao_dias)
    if novo - exp > timedelta(hours=1):
        s.expira_em = novo
        db.commit()
    return u


def sair(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(SessaoUsuario).where(SessaoUsuario.token_hash == _hash_token(token)))
        db.commit()


def encerrar_sessoes(db: Session, usuario_id: int, exceto_token: str | None = None) -> None:
    q = delete(SessaoUsuario).where(SessaoUsuario.usuario_id == usuario_id)
    if exceto_token:
        q = q.where(SessaoUsuario.token_hash != _hash_token(exceto_token))
    db.execute(q)


def _escritorio_do_cadastro(db: Session, nome: str) -> Escritorio:
    """Sem usuário e com um escritório já no banco: o primeiro cadastro assume esse escritório.
    Banco vazio, ou que já tem usuário, cria outro."""
    n_usuarios = int(db.scalar(select(func.count()).select_from(Usuario)) or 0)
    if n_usuarios == 0:
        escritorios = list(db.scalars(select(Escritorio).order_by(Escritorio.id)))
        if len(escritorios) == 1:
            escritorios[0].nome = nome
            return escritorios[0]
    esc = Escritorio(nome=nome)
    db.add(esc)
    db.flush()
    return esc


def criar_usuario(db: Session, email: str, nome: str, senha: str, *, trocar_senha: bool = True) -> Usuario:
    email = normalizar_email(email)
    if "@" not in email or len(email) > 200:
        raise ErroLogin("E-mail inválido.")
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        raise ErroLogin("Já existe um usuário com esse e-mail.")
    validar_nova_senha(senha)
    nome_limpo = (nome or "").strip() or email
    esc = _escritorio_do_cadastro(db, nome_limpo)
    u = Usuario(email=email, nome=nome_limpo, senha_hash=gerar_hash(senha), ativo=True,
                trocar_senha=trocar_senha, criado_em=agora(), escritorio_id=esc.id)
    db.add(u)
    db.flush()
    return u
