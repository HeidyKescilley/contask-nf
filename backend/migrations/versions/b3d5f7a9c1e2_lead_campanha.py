"""leads de campanha (Black Friday): contato, notas por mês e aceite de WhatsApp

Revision ID: b3d5f7a9c1e2
Revises: a2c4e6f8b0d1
Create Date: 2026-11-23 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3d5f7a9c1e2"
down_revision: Union[str, Sequence[str], None] = "a2c4e6f8b0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lead") as t:
        t.add_column(sa.Column("campanha", sa.String(30), nullable=True))
        t.add_column(sa.Column("contato", sa.String(200), nullable=True))
        t.add_column(sa.Column("notas_mes", sa.String(20), nullable=True))
        t.add_column(sa.Column("aceita_whatsapp", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("lead") as t:
        t.drop_column("aceita_whatsapp")
        t.drop_column("notas_mes")
        t.drop_column("contato")
        t.drop_column("campanha")
