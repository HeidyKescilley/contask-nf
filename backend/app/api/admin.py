"""Painel do administrador do sistema (suporte do Contask): escritórios e usuários de todos os clientes.

Só quem tem `usuario.admin_sistema` entra aqui. Esse papel não é concedido pela tela: só no servidor,
por SSH (`contask.sh usuario admin EMAIL`). O painel não mostra dados fiscais dos escritórios
(empresas, notas, certificados): só contas e contagens.
"""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import autenticacao as auth
from app.core.db import sessao
from app.models import Empresa, Escritorio, Usuario

router = APIRouter(prefix="/api/admin", tags=["admin"])


def exigir_admin(request: Request) -> Usuario:
    u = getattr(request.state, "usuario", None)
    if u is None or not u.admin_sistema:
        raise HTTPException(403, "Área restrita ao administrador do sistema.")
    return u


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _usuario_out(u: Usuario) -> dict:
    return {"id": u.id, "escritorio_id": u.escritorio_id, "email": u.email, "nome": u.nome, "ativo": u.ativo,
            "trocar_senha": u.trocar_senha, "admin_sistema": u.admin_sistema,
            "criado_em": _utc(u.criado_em), "ultimo_acesso_em": _utc(u.ultimo_acesso_em)}


class NovoEscritorio(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    email: str
    nome_usuario: str = ""


class NovoUsuario(BaseModel):
    email: str
    nome: str = ""


class Ativo(BaseModel):
    ativo: bool


@router.get("/escritorios")
def listar(db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    n_emp = dict(db.execute(select(Empresa.escritorio_id, func.count()).group_by(Empresa.escritorio_id)).all())
    usuarios: dict[int, list] = {}
    for u in db.scalars(select(Usuario).order_by(Usuario.email)):
        usuarios.setdefault(u.escritorio_id, []).append(_usuario_out(u))
    return [{"id": e.id, "nome": e.nome, "empresas": n_emp.get(e.id, 0), "usuarios": usuarios.get(e.id, [])}
            for e in db.scalars(select(Escritorio).order_by(Escritorio.nome))]


def _criar(db: Session, email: str, nome: str, **kw) -> dict:
    senha = auth.senha_aleatoria()
    try:
        u = auth.criar_usuario(db, email, nome, senha, trocar_senha=True, **kw)
    except auth.ErroLogin as e:
        db.rollback()
        raise HTTPException(409 if "Já existe" in str(e) else 422, str(e)) from None
    db.commit()
    # A senha inicial só aparece nesta resposta (não é gravada nem vai para log)
    return {"usuario": _usuario_out(u), "senha_inicial": senha}


@router.post("/escritorios", status_code=201)
def criar_escritorio(d: NovoEscritorio, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    return _criar(db, d.email, d.nome_usuario, novo_escritorio=d.nome)


@router.post("/escritorios/{escritorio_id}/usuarios", status_code=201)
def criar_usuario(escritorio_id: int, d: NovoUsuario, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    if db.get(Escritorio, escritorio_id) is None:
        raise HTTPException(404, "Escritório não encontrado.")
    return _criar(db, d.email, d.nome, escritorio_id=escritorio_id)


def _usuario(db: Session, usuario_id: int) -> Usuario:
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    return u


@router.post("/usuarios/{usuario_id}/senha")
def nova_senha(usuario_id: int, db: Session = Depends(sessao), adm: Usuario = Depends(exigir_admin)):
    u = _usuario(db, usuario_id)
    if u.id == adm.id:
        raise HTTPException(409, "Para a sua própria senha, use Trocar senha no menu do usuário.")
    senha = auth.senha_aleatoria()
    u.senha_hash, u.trocar_senha, u.ativo = auth.gerar_hash(senha), True, True
    auth.encerrar_sessoes(db, u.id)
    db.commit()
    return {"usuario": _usuario_out(u), "senha_inicial": senha}


@router.put("/usuarios/{usuario_id}/ativo")
def definir_ativo(usuario_id: int, d: Ativo, db: Session = Depends(sessao), adm: Usuario = Depends(exigir_admin)):
    u = _usuario(db, usuario_id)
    if u.id == adm.id and not d.ativo:
        raise HTTPException(409, "Você não pode desativar o próprio acesso.")
    u.ativo = d.ativo
    if not d.ativo:
        auth.encerrar_sessoes(db, u.id)
    db.commit()
    return _usuario_out(u)
