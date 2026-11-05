"""Cadastro, login, saída e troca de senha."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import autenticacao as auth
from app.core.config import config
from app.core.db import sessao
from app.models import Empresa, Escritorio

router = APIRouter(prefix="/api/auth", tags=["login"])


class Entrada(BaseModel):
    email: str
    senha: str


class Cadastro(BaseModel):
    nome: str
    email: str
    senha: str


class TrocaSenha(BaseModel):
    senha_atual: str
    senha_nova: str


def _usuario_json(u) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "email": u.email, "nome": u.nome, "trocar_senha": u.trocar_senha}


def _eu(db: Session, u) -> dict:
    if u is None:
        return {"usuario": None, "escritorio": None, "tem_contabilidade": False, "empresas": 0}
    esc = db.get(Escritorio, u.escritorio_id)
    empresas = int(db.scalar(select(func.count()).select_from(Empresa).where(Empresa.escritorio_id == u.escritorio_id)) or 0)
    tem = db.scalar(select(Empresa.id).where(Empresa.escritorio_id == u.escritorio_id, Empresa.is_contabilidade))
    return {
        "usuario": _usuario_json(u),
        "escritorio": {"id": esc.id, "nome": esc.nome} if esc else None,
        "tem_contabilidade": tem is not None,
        "empresas": empresas,
    }


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "?"


def _cookie(response: Response, token: str) -> None:
    cfg = config()
    response.set_cookie(auth.COOKIE, token, max_age=cfg.sessao_dias * 86400, httponly=True,
                        secure=cfg.cookie_secure, samesite="strict", path="/")


@router.get("/eu")
def eu(request: Request, db: Session = Depends(sessao)):
    u = auth.usuario_da_sessao(db, request.cookies.get(auth.COOKIE))
    return _eu(db, u)


@router.post("/cadastrar", status_code=201)
def cadastrar(dados: Cadastro, request: Request, response: Response, db: Session = Depends(sessao)):
    try:
        auth.criar_usuario(db, dados.email, dados.nome, dados.senha, trocar_senha=False)
        db.commit()
        u, token = auth.entrar(db, dados.email, dados.senha, ip_cliente(request))
    except auth.ErroLogin as e:
        db.rollback()
        status = 409 if "Já existe" in str(e) else 400
        raise HTTPException(status, str(e)) from None
    _cookie(response, token)
    return _eu(db, u)


@router.post("/entrar")
def entrar(dados: Entrada, request: Request, response: Response, db: Session = Depends(sessao)):
    try:
        u, token = auth.entrar(db, dados.email, dados.senha, ip_cliente(request))
    except auth.ErroLogin as e:
        raise HTTPException(401, str(e)) from None
    _cookie(response, token)
    return {"usuario": _usuario_json(u)}


@router.post("/sair", status_code=204)
def sair(request: Request, response: Response, db: Session = Depends(sessao)):
    auth.sair(db, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    response.status_code = 204
    return response


@router.post("/senha")
def trocar_senha(dados: TrocaSenha, request: Request, db: Session = Depends(sessao)):
    token = request.cookies.get(auth.COOKIE)
    u = auth.usuario_da_sessao(db, token)
    if u is None:
        raise HTTPException(401, "Entre de novo para trocar a senha.")
    chaves = (f"ip:{ip_cliente(request)}", f"email:{u.email}")
    if auth.limitador.bloqueado(*chaves):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    if not auth.conferir_senha(dados.senha_atual, u.senha_hash):
        auth.limitador.falhou(*chaves)
        raise HTTPException(400, "A senha atual está incorreta.")
    if dados.senha_nova == dados.senha_atual:
        raise HTTPException(400, "A nova senha precisa ser diferente da atual.")
    try:
        auth.validar_nova_senha(dados.senha_nova)
    except auth.ErroLogin as e:
        raise HTTPException(400, str(e)) from None
    u.senha_hash = auth.gerar_hash(dados.senha_nova)
    u.trocar_senha = False
    auth.encerrar_sessoes(db, u.id, exceto_token=token)
    db.commit()
    return {"usuario": _usuario_json(u)}
