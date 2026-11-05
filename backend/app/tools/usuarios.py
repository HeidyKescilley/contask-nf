"""Usuários do servidor na internet.

    python -m app.tools.usuarios criar EMAIL "NOME"      # gera senha inicial e mostra uma única vez
    python -m app.tools.usuarios redefinir EMAIL          # nova senha inicial (troca obrigatória)
    python -m app.tools.usuarios desativar EMAIL
    python -m app.tools.usuarios listar

A senha gerada aparece só na tela de quem rodou o comando (nunca em log). No primeiro acesso,
o sistema obriga a pessoa a trocar.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core import autenticacao as auth
from app.core.db import nova_sessao
from app.core.migracao import migrar
from app.models import Usuario


def _buscar(db, email: str) -> Usuario:
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == auth.normalizar_email(email)))
    if u is None:
        sys.exit(f"Usuário não encontrado: {email}")
    return u


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Usuários do Contask NF.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar")
    c.add_argument("email")
    c.add_argument("nome", nargs="?", default="")
    r = sub.add_parser("redefinir")
    r.add_argument("email")
    d = sub.add_parser("desativar")
    d.add_argument("email")
    sub.add_parser("listar")
    a = ap.parse_args(argv)

    migrar()
    with nova_sessao() as db:
        if a.cmd == "criar":
            senha = auth.senha_aleatoria()
            try:
                u = auth.criar_usuario(db, a.email, a.nome, senha, trocar_senha=True)
            except auth.ErroLogin as e:
                sys.exit(str(e))
            db.commit()
            print(f"Usuário criado: {u.email}\nSenha inicial (troca obrigatória no primeiro acesso): {senha}")
        elif a.cmd == "redefinir":
            u = _buscar(db, a.email)
            senha = auth.senha_aleatoria()
            u.senha_hash, u.trocar_senha, u.ativo = auth.gerar_hash(senha), True, True
            auth.encerrar_sessoes(db, u.id)
            db.commit()
            print(f"Nova senha inicial de {u.email} (troca obrigatória): {senha}")
        elif a.cmd == "desativar":
            u = _buscar(db, a.email)
            u.ativo = False
            auth.encerrar_sessoes(db, u.id)
            db.commit()
            print(f"Usuário desativado: {u.email}")
        else:
            for u in db.scalars(select(Usuario).order_by(Usuario.email)):
                acesso = f"{u.ultimo_acesso_em:%d/%m/%Y %H:%M}" if u.ultimo_acesso_em else "nunca"
                print(f"{u.email:40} {'ativo' if u.ativo else 'inativo':8} último acesso: {acesso}  {u.nome}")


if __name__ == "__main__":
    main()
