"""Login, saída e troca de senha (servidor na internet)."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import autenticacao as auth
from app.core.config import config
from app.core.db import sessao

router = APIRouter(prefix="/api/auth", tags=["login"])


class Entrada(BaseModel):
    email: str
    senha: str


class TrocaSenha(BaseModel):
    senha_atual: str
    senha_nova: str


def _usuario_json(u) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "email": u.email, "nome": u.nome, "trocar_senha": u.trocar_senha}


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/eu")
def eu(request: Request, db: Session = Depends(sessao)):
    cfg = config()
    u = auth.usuario_da_sessao(db, request.cookies.get(auth.COOKIE)) if cfg.login_ativo else None
    return {"login_ativo": cfg.login_ativo, "usuario": _usuario_json(u)}


@router.post("/entrar")
def entrar(dados: Entrada, request: Request, response: Response, db: Session = Depends(sessao)):
    if not config().login_ativo:
        raise HTTPException(400, "O login não está ativo nesta instalação.")
    try:
        u, token = auth.entrar(db, dados.email, dados.senha, ip_cliente(request))
    except auth.ErroLogin as e:
        raise HTTPException(401, str(e)) from None
    cfg = config()
    response.set_cookie(auth.COOKIE, token, max_age=cfg.sessao_dias * 86400, httponly=True,
                        secure=cfg.cookie_seguro, samesite="strict", path="/")
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
    auth.encerrar_sessoes(db, u.id, exceto_token=token)  # derruba outras sessões abertas
    db.commit()
    return {"usuario": _usuario_json(u)}
