"""emissor: cIndOp e cClassTrib gravados na nota (o ISSNet do DF exige o grupo IBSCBS)

Revision ID: c4e8a2b6d0f1
Revises: b3d7f1a9c5e2
Create Date: 2026-11-15 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e8a2b6d0f1"
down_revision: Union[str, Sequence[str], None] = "b3d7f1a9c5e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.add_column(sa.Column("cindop", sa.String(6), nullable=True))
        batch.add_column(sa.Column("cclasstrib", sa.String(6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.drop_column("cclasstrib")
        batch.drop_column("cindop")
