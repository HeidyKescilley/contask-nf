"""sessão com área: cliente (o sistema) ou admin (a administração, separada)

Revision ID: a8c0e2f4b6d7
Revises: f7b9d1e3a5c6
Create Date: 2026-11-25 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8c0e2f4b6d7"
down_revision: Union[str, Sequence[str], None] = "f7b9d1e3a5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessao_usuario") as b:
        b.add_column(sa.Column("area", sa.String(10), nullable=False, server_default="cliente"))


def downgrade() -> None:
    with op.batch_alter_table("sessao_usuario") as b:
        b.drop_column("area")
