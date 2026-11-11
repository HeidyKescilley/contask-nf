"""Painel do administrador do sistema (suporte do Contask): escritórios e usuários de todos os clientes.

Só quem tem `usuario.admin_sistema` entra aqui. Esse papel não é concedido pela tela: só no servidor,
por SSH (`contask.sh usuario admin EMAIL`). O painel não mostra dados fiscais dos escritórios
(empresas, notas, certificados): só contas e contagens.
"""
from __future__ import annotations

from datetime import date, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import autenticacao as auth
from app.core import escritorios as regras
from app.core.db import sessao
from app.core.uso import xmls_no_mes
from app.models import Empresa, Escritorio, EscritorioEvento, Usuario

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


class Plano(BaseModel):
    situacao: str = "ativo"
    teste_ate: date | None = None
    limite_xmls_mes: int | None = Field(None, ge=0)
    mensalidade: Decimal | None = Field(None, ge=0)
    dia_vencimento: int | None = Field(None, ge=1, le=31)
    proximo_vencimento: date | None = None
    observacoes: str | None = Field(None, max_length=2000)


class NovoEscritorio(Plano):
    nome: str = Field(min_length=2, max_length=200)
    email: str
    nome_usuario: str = ""


class EdicaoEscritorio(Plano):
    nome: str = Field(min_length=2, max_length=200)


class Pagamento(BaseModel):
    valor: Decimal | None = Field(None, ge=0)
    data: date | None = None
    observacao: str | None = Field(None, max_length=300)


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
    return [_escritorio_out(db, e, n_emp.get(e.id, 0), usuarios.get(e.id, []))
            for e in db.scalars(select(Escritorio).order_by(Escritorio.nome))]


ROTULOS = {"teste": "Em teste", "ativo": "Ativo", "suspenso": "Suspenso"}


def _f(v):
    return float(v) if v is not None else None


def _escritorio_out(db: Session, e: Escritorio, n_emp: int, usuarios: list) -> dict:
    hoje = regras.hoje()
    venc = e.proximo_vencimento
    atraso = (hoje - venc).days if venc is not None and venc < hoje and e.situacao == "ativo" else 0
    return {
        "id": e.id, "nome": e.nome, "empresas": n_emp, "usuarios": usuarios,
        "situacao": e.situacao, "teste_ate": e.teste_ate, "bloqueio": regras.motivo_bloqueio(e),
        "limite_xmls_mes": e.limite_xmls_mes, "limite_efetivo": regras.limite_xmls(db, e.id),
        "xmls_no_mes": xmls_no_mes(db, e.id),
        "mensalidade": _f(e.mensalidade), "dia_vencimento": e.dia_vencimento, "proximo_vencimento": venc,
        "dias_atraso": atraso, "observacoes": e.observacoes, "criado_em": _utc(e.criado_em),
    }


def _detalhe(db: Session, e: Escritorio) -> dict:
    n = db.scalar(select(func.count()).select_from(Empresa).where(Empresa.escritorio_id == e.id)) or 0
    us = [_usuario_out(u) for u in db.scalars(select(Usuario).where(Usuario.escritorio_id == e.id).order_by(Usuario.email))]
    return _escritorio_out(db, e, n, us)


def _evento(db: Session, esc_id: int, adm: Usuario, tipo: str, descricao: str, valor=None) -> None:
    db.add(EscritorioEvento(escritorio_id=esc_id, usuario_id=adm.id, tipo=tipo, descricao=descricao, valor=valor))


def _aplicar_plano(db: Session, e: Escritorio, d: Plano, adm: Usuario) -> None:
    if d.situacao not in regras.SITUACOES:
        raise HTTPException(422, "Situação inválida: use teste, ativo ou suspenso.")
    if d.situacao == "suspenso":
        admins = db.scalar(select(func.count()).select_from(Usuario).where(
            Usuario.escritorio_id == e.id, Usuario.admin_sistema)) or 0
        if admins:
            raise HTTPException(409, "Este escritório tem um administrador do sistema: ele não pode ser suspenso.")
    antes = e.situacao
    mudancas = []
    for campo in ("teste_ate", "limite_xmls_mes", "mensalidade", "dia_vencimento", "proximo_vencimento", "observacoes"):
        novo = getattr(d, campo)
        if campo == "observacoes":
            novo = (novo or "").strip() or None
        atual = getattr(e, campo)
        if campo == "mensalidade" and _f(atual) == _f(novo):
            continue
        if atual != novo:
            setattr(e, campo, novo)
            if campo != "observacoes":
                mudancas.append(campo.replace("_", " "))
    if e.dia_vencimento and e.proximo_vencimento is None:
        h = regras.hoje()
        v = regras.no_dia(h.year, h.month, e.dia_vencimento)
        e.proximo_vencimento = v if v >= h else regras.mes_seguinte(v, e.dia_vencimento)
    e.situacao = d.situacao
    if antes != d.situacao:
        _evento(db, e.id, adm, "situacao", f"Situação: {ROTULOS.get(antes, antes)} para {ROTULOS[d.situacao]}")
    if mudancas:
        _evento(db, e.id, adm, "plano", "Alterado: " + ", ".join(mudancas))


def _esc(db: Session, escritorio_id: int) -> Escritorio:
    e = db.get(Escritorio, escritorio_id)
    if e is None:
        raise HTTPException(404, "Escritório não encontrado.")
    return e


@router.put("/escritorios/{escritorio_id}")
def editar_escritorio(escritorio_id: int, d: EdicaoEscritorio, db: Session = Depends(sessao),
                      adm: Usuario = Depends(exigir_admin)):
    e = _esc(db, escritorio_id)
    if e.nome != d.nome.strip():
        _evento(db, e.id, adm, "plano", f"Nome: {e.nome} para {d.nome.strip()}")
        e.nome = d.nome.strip()
    _aplicar_plano(db, e, d, adm)
    db.commit()
    return _detalhe(db, e)


@router.post("/escritorios/{escritorio_id}/pagamento")
def registrar_pagamento(escritorio_id: int, d: Pagamento, db: Session = Depends(sessao),
                        adm: Usuario = Depends(exigir_admin)):
    """Registra o pagamento e empurra o vencimento um mês (a cobrança é feita fora do sistema)."""
    e = _esc(db, escritorio_id)
    valor = d.valor if d.valor is not None else e.mensalidade
    referente = e.proximo_vencimento
    if referente is not None:
        e.proximo_vencimento = regras.mes_seguinte(referente, e.dia_vencimento)
    texto = f"Pagamento recebido em {(d.data or regras.hoje()):%d/%m/%Y}"
    if referente:
        texto += f", referente ao vencimento de {referente:%d/%m/%Y}"
    if (d.observacao or "").strip():
        texto += f". {d.observacao.strip()}"
    _evento(db, e.id, adm, "pagamento", texto, valor)
    db.commit()
    return _detalhe(db, e)


@router.get("/escritorios/{escritorio_id}/historico")
def historico(escritorio_id: int, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    _esc(db, escritorio_id)
    nomes = {u.id: u.nome or u.email for u in db.scalars(select(Usuario))}
    return [{"id": ev.id, "momento": _utc(ev.momento), "tipo": ev.tipo, "descricao": ev.descricao,
             "valor": _f(ev.valor), "por": nomes.get(ev.usuario_id)}
            for ev in db.scalars(select(EscritorioEvento).where(EscritorioEvento.escritorio_id == escritorio_id)
                                 .order_by(EscritorioEvento.momento.desc(), EscritorioEvento.id.desc()).limit(200))]


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
def criar_escritorio(d: NovoEscritorio, db: Session = Depends(sessao), adm: Usuario = Depends(exigir_admin)):
    senha = auth.senha_aleatoria()
    try:
        u = auth.criar_usuario(db, d.email, d.nome_usuario, senha, trocar_senha=True, novo_escritorio=d.nome)
    except auth.ErroLogin as ex:
        db.rollback()
        raise HTTPException(409 if "Já existe" in str(ex) else 422, str(ex)) from None
    e = db.get(Escritorio, u.escritorio_id)
    e.situacao = d.situacao if d.situacao in regras.SITUACOES else "ativo"  # sem evento de "mudança" na criação
    _aplicar_plano(db, e, d, adm)
    _evento(db, e.id, adm, "criado", f"Escritório criado ({ROTULOS[e.situacao]}), primeiro usuário {u.email}")
    db.commit()
    # A senha inicial só aparece nesta resposta (não é gravada nem vai para log)
    return {"usuario": _usuario_out(u), "senha_inicial": senha}


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
