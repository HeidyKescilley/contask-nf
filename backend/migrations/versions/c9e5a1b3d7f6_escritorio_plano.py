"""escritório: situação, plano, mensalidade e histórico

Revision ID: c9e5a1b3d7f6
Revises: b8d4f0a2c6e5
Create Date: 2026-11-11 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c9e5a1b3d7f6"
down_revision: Union[str, Sequence[str], None] = "b8d4f0a2c6e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("escritorio") as batch:
        batch.add_column(sa.Column("situacao", sa.String(10), nullable=False, server_default="ativo"))
        batch.add_column(sa.Column("teste_ate", sa.Date(), nullable=True))
        batch.add_column(sa.Column("limite_xmls_mes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("mensalidade", sa.Numeric(10, 2), nullable=True))
        batch.add_column(sa.Column("dia_vencimento", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("proximo_vencimento", sa.Date(), nullable=True))
        batch.add_column(sa.Column("observacoes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "escritorio_evento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("valor", sa.Numeric(10, 2), nullable=True),
    )
    op.create_index("ix_escritorio_evento_escritorio_id", "escritorio_evento", ["escritorio_id"])


def downgrade() -> None:
    op.drop_table("escritorio_evento")
    with op.batch_alter_table("escritorio") as batch:
        for c in ("criado_em", "observacoes", "proximo_vencimento", "dia_vencimento", "mensalidade",
                  "limite_xmls_mes", "teste_ate", "situacao"):
            batch.drop_column(c)
