"""segundo certificado de procurador da contabilidade e o certificado com procuração de cada empresa

Revision ID: d5f7b9c1e3a4
Revises: c4e6a8b0d2f3
Create Date: 2026-11-24 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5f7b9c1e3a4"
down_revision: Union[str, Sequence[str], None] = "c4e6a8b0d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("empresa") as b:
        # Na contabilidade: segundo certificado de procurador (em geral o e-CPF do contador)
        b.add_column(sa.Column("certificado_extra_id", sa.Integer(), nullable=True))
        # Na empresa por procuração: qual certificado da contabilidade tem a procuração (descoberto na busca)
        b.add_column(sa.Column("certificado_procurador_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_empresa_certificado_extra", "certificado", ["certificado_extra_id"], ["id"], ondelete="SET NULL")
        b.create_foreign_key("fk_empresa_certificado_procurador", "certificado", ["certificado_procurador_id"], ["id"],
                             ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("empresa") as b:
        b.drop_constraint("fk_empresa_certificado_procurador", type_="foreignkey")
        b.drop_constraint("fk_empresa_certificado_extra", type_="foreignkey")
        b.drop_column("certificado_procurador_id")
        b.drop_column("certificado_extra_id")
