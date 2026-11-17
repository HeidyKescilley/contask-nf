"""emissor: substituição de NFS-e (grupo subst da DPS)

Revision ID: d7a3c9e1f5b2
Revises: c4e8a2b6d0f1
Create Date: 2026-11-17 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d7a3c9e1f5b2"
down_revision: Union[str, Sequence[str], None] = "c4e8a2b6d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.add_column(sa.Column("subst_chave", sa.String(50), nullable=True))
        batch.add_column(sa.Column("subst_motivo", sa.String(2), nullable=True))
        batch.add_column(sa.Column("subst_justificativa", sa.Text(), nullable=True))
        batch.add_column(sa.Column("substituida_por_id", sa.Integer(), nullable=True))
        batch.create_index("ix_nota_emitida_subst_chave", ["subst_chave"])
        batch.create_foreign_key("fk_nota_emitida_substituida_por", "nota_emitida", ["substituida_por_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.drop_constraint("fk_nota_emitida_substituida_por", type_="foreignkey")
        batch.drop_index("ix_nota_emitida_subst_chave")
        batch.drop_column("substituida_por_id")
        batch.drop_column("subst_justificativa")
        batch.drop_column("subst_motivo")
        batch.drop_column("subst_chave")
