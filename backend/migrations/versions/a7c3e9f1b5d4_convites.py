"""convites de cadastro de escritório

Revision ID: a7c3e9f1b5d4
Revises: f6a2b4c8d1e3
Create Date: 2026-11-10 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c3e9f1b5d4"
down_revision: Union[str, Sequence[str], None] = "f6a2b4c8d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "convite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("descricao", sa.String(200), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("convite")
