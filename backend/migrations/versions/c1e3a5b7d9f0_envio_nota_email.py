"""envio da NFS-e por e-mail: histórico, opção na recorrente e pendência na nota emitida

Revision ID: c1e3a5b7d9f0
Revises: b9d1f3a5c7e8
Create Date: 2026-11-26 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1e3a5b7d9f0"
down_revision: Union[str, Sequence[str], None] = "b9d1f3a5c7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nota_envio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chave", sa.String(50), nullable=False),
        sa.Column("nota_id", sa.Integer(), sa.ForeignKey("nota.id", ondelete="SET NULL")),
        sa.Column("nota_emitida_id", sa.Integer(), sa.ForeignKey("nota_emitida.id", ondelete="SET NULL")),
        sa.Column("recorrente_id", sa.Integer(), sa.ForeignKey("nota_recorrente.id", ondelete="SET NULL")),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL")),
        sa.Column("para", sa.Text(), nullable=False),
        sa.Column("situacao", sa.String(10), nullable=False),
        sa.Column("erro", sa.Text()),
        sa.Column("automatico", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_nota_envio_escritorio_criado", "nota_envio", ["escritorio_id", "criado_em"])
    op.create_index("ix_nota_envio_empresa_id", "nota_envio", ["empresa_id"])
    op.create_index("ix_nota_envio_chave", "nota_envio", ["chave"])
    with op.batch_alter_table("nota_recorrente") as b:
        b.add_column(sa.Column("email_enviar", sa.Boolean(), nullable=False, server_default="0"))
        b.add_column(sa.Column("email_para", sa.Text()))
        b.add_column(sa.Column("email_mensagem", sa.Text()))
    with op.batch_alter_table("nota_emitida") as b:
        b.add_column(sa.Column("email_pendente", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("nota_emitida") as b:
        b.drop_column("email_pendente")
    with op.batch_alter_table("nota_recorrente") as b:
        b.drop_column("email_mensagem")
        b.drop_column("email_para")
        b.drop_column("email_enviar")
    op.drop_table("nota_envio")
