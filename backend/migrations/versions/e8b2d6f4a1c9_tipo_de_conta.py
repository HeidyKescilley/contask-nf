"""escritório: tipo de conta (contador ou empresa)

Revision ID: e8b2d6f4a1c9
Revises: d1f7b3c5e9a2
Create Date: 2026-11-13 09:00:00

contador: escritório de contabilidade com várias empresas clientes (o que já existia).
empresa: a própria empresa que emite as notas; um CNPJ só, sem cadastrar outros.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e8b2d6f4a1c9"
down_revision: Union[str, Sequence[str], None] = "d1f7b3c5e9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("escritorio") as batch:
        batch.add_column(sa.Column("tipo", sa.String(10), nullable=False, server_default="contador"))


def downgrade() -> None:
    with op.batch_alter_table("escritorio") as batch:
        batch.drop_column("tipo")
