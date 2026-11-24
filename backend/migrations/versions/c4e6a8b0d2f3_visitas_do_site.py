"""visitas do site de vendas (sem cookie, sem IP)

Revision ID: c4e6a8b0d2f3
Revises: b3d5f7a9c1e2
Create Date: 2026-11-23 21:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e6a8b0d2f3"
down_revision: Union[str, Sequence[str], None] = "b3d5f7a9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visita",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("pagina", sa.String(120), nullable=False),
        sa.Column("canal", sa.String(60), nullable=False),
        sa.Column("meio", sa.String(60), nullable=True),
        sa.Column("campanha", sa.String(100), nullable=True),
        sa.Column("referencia", sa.String(120), nullable=True),
        sa.Column("dispositivo", sa.String(12), nullable=False),
        sa.Column("visitante", sa.String(16), nullable=False),
    )
    op.create_index("ix_visita_dia", "visita", ["dia"])


def downgrade() -> None:
    op.drop_index("ix_visita_dia", "visita")
    op.drop_table("visita")
