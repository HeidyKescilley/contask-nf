"""usuário administrador do sistema

Revision ID: b8d4f0a2c6e5
Revises: a7c3e9f1b5d4
Create Date: 2026-11-11 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d4f0a2c6e5"
down_revision: Union[str, Sequence[str], None] = "a7c3e9f1b5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.add_column(sa.Column("admin_sistema", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.drop_column("admin_sistema")
