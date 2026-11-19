"""emissor: texto fixo das informações complementares por empresa

Revision ID: f1c5e7a9b3d4
Revises: e9b4d2f6a8c1
Create Date: 2026-11-19 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1c5e7a9b3d4"
down_revision: Union[str, Sequence[str], None] = "e9b4d2f6a8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.add_column(sa.Column("texto_fixo", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.drop_column("texto_fixo")
