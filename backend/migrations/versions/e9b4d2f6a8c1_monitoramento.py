"""monitoramento do uso: eventos, gravações, pesquisa e suporte

Revision ID: e9b4d2f6a8c1
Revises: d7a3c9e1f5b2
Create Date: 2026-11-19 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e9b4d2f6a8c1"
down_revision: Union[str, Sequence[str], None] = "d7a3c9e1f5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _escritorio():
    return sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="CASCADE"), nullable=False)


def _usuario(nulo=False):
    return sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL" if nulo else "CASCADE"),
                     nullable=nulo)


def upgrade() -> None:
    op.create_table(
        "uso_evento",
        sa.Column("id", sa.Integer(), primary_key=True),
        _escritorio(), _usuario(),
        sa.Column("sessao", sa.String(40), nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=True),
    )
    for col in ("escritorio_id", "usuario_id", "sessao", "momento"):
        op.create_index(f"ix_uso_evento_{col}", "uso_evento", [col])
    op.create_index("ix_uso_evento_tipo_momento", "uso_evento", ["tipo", "momento"])

    op.create_table(
        "gravacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        _escritorio(), _usuario(),
        sa.Column("sessao", sa.String(40), nullable=False, unique=True),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pagina_inicial", sa.String(120), nullable=True),
        sa.Column("paginas", sa.JSON(), nullable=True),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arquivo", sa.String(300), nullable=False),
    )
    for col in ("escritorio_id", "usuario_id", "iniciado_em"):
        op.create_index(f"ix_gravacao_{col}", "gravacao", [col])

    op.create_table(
        "pesquisa_resposta",
        sa.Column("id", sa.Integer(), primary_key=True),
        _escritorio(), _usuario(),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adiada", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("decepcao", sa.String(10), nullable=True),
        sa.Column("horas", sa.Integer(), nullable=True),
        sa.Column("nps", sa.Integer(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
    )
    for col in ("escritorio_id", "usuario_id"):
        op.create_index(f"ix_pesquisa_resposta_{col}", "pesquisa_resposta", [col])

    op.create_table(
        "pedido_suporte",
        sa.Column("id", sa.Integer(), primary_key=True),
        _escritorio(), _usuario(nulo=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assunto", sa.String(20), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("pagina", sa.String(120), nullable=True),
        sa.Column("situacao", sa.String(10), nullable=False, server_default="aberto"),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("escritorio_id", "momento"):
        op.create_index(f"ix_pedido_suporte_{col}", "pedido_suporte", [col])


def downgrade() -> None:
    op.drop_table("pedido_suporte")
    op.drop_table("pesquisa_resposta")
    op.drop_table("gravacao")
    op.drop_table("uso_evento")
