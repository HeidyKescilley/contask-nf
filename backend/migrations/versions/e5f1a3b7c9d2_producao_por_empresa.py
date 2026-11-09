"""emissor: liberação de produção por empresa

Revision ID: e5f1a3b7c9d2
Revises: d4e9f3a2b8c5
Create Date: 2026-11-09 10:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f1a3b7c9d2"
down_revision: Union[str, Sequence[str], None] = "d4e9f3a2b8c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.add_column(sa.Column("producao_liberada", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Quem já emitiu em produção (o piloto) continua liberado
    op.execute("UPDATE emissor_empresa SET producao_liberada = 1 WHERE empresa_id IN "
               "(SELECT DISTINCT empresa_id FROM nota_emitida WHERE ambiente = 1)")


def downgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.drop_column("producao_liberada")
