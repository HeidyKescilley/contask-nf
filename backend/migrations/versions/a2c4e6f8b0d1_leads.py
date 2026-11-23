"""leads do formulário de teste grátis do site

Revision ID: a2c4e6f8b0d1
Revises: f1c5e7a9b3d4
Create Date: 2026-11-23 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a2c4e6f8b0d1"
down_revision: Union[str, Sequence[str], None] = "f1c5e7a9b3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("segmento", sa.String(20), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("telefone", sa.String(20), nullable=False),
        sa.Column("origem", sa.String(300), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="SET NULL"), nullable=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_status", sa.String(12), nullable=False),
        sa.Column("email_enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_erro", sa.String(300), nullable=True),
        sa.Column("etapa", sa.String(12), nullable=False, server_default="novo"),
        sa.Column("observacoes", sa.Text(), nullable=True),
    )
    op.create_index("ix_lead_criado_em", "lead", ["criado_em"])
    op.create_index("ix_lead_email", "lead", ["email"])


def downgrade() -> None:
    op.drop_index("ix_lead_email", "lead")
    op.drop_index("ix_lead_criado_em", "lead")
    op.drop_table("lead")
