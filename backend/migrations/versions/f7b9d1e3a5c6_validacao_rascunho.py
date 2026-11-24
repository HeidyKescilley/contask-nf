"""resultado da validação guardado no rascunho

Revision ID: f7b9d1e3a5c6
Revises: e6a8c0d2f4b5
Create Date: 2026-11-24 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7b9d1e3a5c6"
down_revision: Union[str, Sequence[str], None] = "e6a8c0d2f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nota_rascunho") as b:
        b.add_column(sa.Column("validacao", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("nota_rascunho") as b:
        b.drop_column("validacao")
