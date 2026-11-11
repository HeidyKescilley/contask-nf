"""Contas do servidor na internet: escritórios, usuários e convites. Só quem tem acesso ao servidor roda.

    python -m app.tools.usuarios escritorios                                   # lista os escritórios
    python -m app.tools.usuarios novo-escritorio "Contábil Silva" EMAIL "NOME"  # escritório + 1º usuário
    python -m app.tools.usuarios criar EMAIL "NOME" --escritorio ID             # mais um usuário no escritório
    python -m app.tools.usuarios redefinir EMAIL                                # nova senha inicial
    python -m app.tools.usuarios desativar EMAIL | reativar EMAIL
    python -m app.tools.usuarios listar
    python -m app.tools.usuarios convite "descrição"                           # só com CONTASK_CADASTRO=convite
    python -m app.tools.usuarios convites

A senha gerada (e o convite) aparecem só na tela de quem rodou o comando, nunca em log. No primeiro
acesso o sistema obriga a pessoa a trocar a senha.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core import autenticacao as auth
from app.core.db import nova_sessao
from app.core.migracao import migrar
from app.models import Convite, Empresa, Escritorio, Usuario


def _buscar(db, email: str) -> Usuario:
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == auth.normalizar_email(email)))
    if u is None:
        sys.exit(f"Usuário não encontrado: {email}")
    return u


def _criar(db, email: str, nome: str, **kw) -> None:
    senha = auth.senha_aleatoria()
    try:
        u = auth.criar_usuario(db, email, nome, senha, trocar_senha=True, **kw)
    except auth.ErroLogin as e:
        sys.exit(str(e))
    db.commit()
    esc = db.get(Escritorio, u.escritorio_id)
    print(f"Escritório: {esc.nome} (id {esc.id})\nUsuário: {u.email}\n"
          f"Senha inicial (troca obrigatória no primeiro acesso): {senha}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Contas do Contask NF (escritórios e usuários).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("escritorios")
    n = sub.add_parser("novo-escritorio")
    n.add_argument("escritorio")
    n.add_argument("email")
    n.add_argument("nome", nargs="?", default="")
    c = sub.add_parser("criar")
    c.add_argument("email")
    c.add_argument("nome", nargs="?", default="")
    c.add_argument("--escritorio", type=int, help="id do escritório (veja o comando escritorios)")
    for nome in ("redefinir", "desativar", "reativar"):
        sub.add_parser(nome).add_argument("email")
    sub.add_parser("listar")
    cv = sub.add_parser("convite")
    cv.add_argument("descricao")
    sub.add_parser("convites")
    a = ap.parse_args(argv)

    migrar()
    with nova_sessao() as db:
        if a.cmd == "escritorios":
            for e in db.scalars(select(Escritorio).order_by(Escritorio.id)):
                nu = db.scalar(select(func.count()).select_from(Usuario).where(Usuario.escritorio_id == e.id)) or 0
                ne = db.scalar(select(func.count()).select_from(Empresa).where(Empresa.escritorio_id == e.id)) or 0
                print(f"{e.id:>4}  {e.nome[:50]:50} {nu} usuário(s)  {ne} empresa(s)")
        elif a.cmd == "novo-escritorio":
            _criar(db, a.email, a.nome, novo_escritorio=a.escritorio)
        elif a.cmd == "criar":
            esc_id = a.escritorio
            if esc_id is None:  # só um escritório (instalação local): é nele
                ids = list(db.scalars(select(Escritorio.id)))
                if len(ids) > 1:
                    sys.exit("Há mais de um escritório: informe --escritorio ID (veja: escritorios). "
                             "Para um escritório novo, use novo-escritorio.")
                esc_id = ids[0] if ids else None
            if esc_id is None:
                _criar(db, a.email, a.nome)
            else:
                _criar(db, a.email, a.nome, escritorio_id=esc_id)
        elif a.cmd == "redefinir":
            u = _buscar(db, a.email)
            senha = auth.senha_aleatoria()
            u.senha_hash, u.trocar_senha, u.ativo = auth.gerar_hash(senha), True, True
            auth.encerrar_sessoes(db, u.id)
            db.commit()
            print(f"Nova senha inicial de {u.email} (troca obrigatória): {senha}")
        elif a.cmd in ("desativar", "reativar"):
            u = _buscar(db, a.email)
            u.ativo = a.cmd == "reativar"
            if not u.ativo:
                auth.encerrar_sessoes(db, u.id)
            db.commit()
            print(f"Usuário {'reativado' if u.ativo else 'desativado'}: {u.email}")
        elif a.cmd == "listar":
            for u in db.scalars(select(Usuario).order_by(Usuario.escritorio_id, Usuario.email)):
                acesso = f"{u.ultimo_acesso_em:%d/%m/%Y %H:%M}" if u.ultimo_acesso_em else "nunca"
                print(f"esc {u.escritorio_id:>3}  {u.email:40} {'ativo' if u.ativo else 'inativo':8} último acesso: {acesso}  {u.nome}")
        elif a.cmd == "convite":
            from app.core import convites
            codigo = convites.gerar(db, a.descricao)
            db.commit()
            print(f"Convite (uso único, vale só com CONTASK_CADASTRO=convite): {codigo}")
        else:
            for cv in db.scalars(select(Convite).order_by(Convite.id)):
                sit = "revogado" if cv.revogado else (f"usado em {cv.usado_em:%d/%m/%Y}" if cv.usado_em else "disponível")
                print(f"{cv.id:>4}  {cv.descricao[:50]:50} {sit}")


if __name__ == "__main__":
    main()
