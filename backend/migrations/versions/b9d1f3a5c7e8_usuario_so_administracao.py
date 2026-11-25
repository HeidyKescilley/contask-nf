"""usuário sem escritório: acesso só à administração

Revision ID: b9d1f3a5c7e8
Revises: a8c0e2f4b6d7
Create Date: 2026-11-25 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9d1f3a5c7e8"
down_revision: Union[str, Sequence[str], None] = "a8c0e2f4b6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuario") as b:
        b.alter_column("escritorio_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM usuario WHERE escritorio_id IS NULL")
    with op.batch_alter_table("usuario") as b:
        b.alter_column("escritorio_id", existing_type=sa.Integer(), nullable=False)
