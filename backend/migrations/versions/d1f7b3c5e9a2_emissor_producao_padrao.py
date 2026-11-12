"""emissor: produção como padrão das empresas emissoras

Revision ID: d1f7b3c5e9a2
Revises: c9e5a1b3d7f6
Create Date: 2026-11-12 09:00:00

Decisão de 12/11/2026 (dona do projeto): toda empresa emissora fica em produção por padrão. Só vale
onde a chave geral CONTASK_EMISSOR_PRODUCAO estiver ligada; sem ela, tudo segue na produção restrita.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1f7b3c5e9a2"
down_revision: Union[str, Sequence[str], None] = "c9e5a1b3d7f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.alter_column("producao_liberada", existing_type=sa.Boolean(), server_default="1")
    op.execute("UPDATE emissor_empresa SET producao_liberada = 1")


def downgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.alter_column("producao_liberada", existing_type=sa.Boolean(), server_default="0")
