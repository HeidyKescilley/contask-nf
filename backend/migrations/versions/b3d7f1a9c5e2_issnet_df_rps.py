"""emissor: canal da nota (Sefin ou ISSNet DF), cTribMun de até 10 dígitos e numeração de RPS do ISSNet

Revision ID: b3d7f1a9c5e2
Revises: e8b2d6f4a1c9
Create Date: 2026-11-15 15:00:00

No ISSNet do DF o código de tributação municipal tem até 10 dígitos e a numeração da DPS (RPS) é
liberada pelo fisco; rps_disponivel guarda cada número e o que aconteceu com ele.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3d7f1a9c5e2"
down_revision: Union[str, Sequence[str], None] = "e8b2d6f4a1c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.add_column(sa.Column("canal", sa.String(10), nullable=False, server_default="nacional"))
        batch.alter_column("ctribmun", type_=sa.String(10), existing_type=sa.String(3), existing_nullable=True)
    with op.batch_alter_table("servico_emissor") as batch:
        batch.alter_column("ctribmun", type_=sa.String(10), existing_type=sa.String(3), existing_nullable=True)
    op.create_table(
        "rps_disponivel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ambiente", sa.Integer(), nullable=False),
        sa.Column("serie", sa.String(5), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("situacao", sa.String(12), nullable=False),
        sa.Column("nota_id", sa.Integer(), sa.ForeignKey("nota_emitida.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("empresa_id", "ambiente", "serie", "numero", name="uq_rps_empresa_numero"),
    )
    op.create_index("ix_rps_disponivel_empresa_id", "rps_disponivel", ["empresa_id"])
    op.create_index("ix_rps_disponivel_situacao", "rps_disponivel", ["situacao"])
    op.create_table(
        "sincronizacao_rps",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ambiente", sa.Integer(), primary_key=True),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disponiveis", sa.Integer(), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sincronizacao_rps")
    op.drop_index("ix_rps_disponivel_situacao", "rps_disponivel")
    op.drop_index("ix_rps_disponivel_empresa_id", "rps_disponivel")
    op.drop_table("rps_disponivel")
    with op.batch_alter_table("servico_emissor") as batch:
        batch.alter_column("ctribmun", type_=sa.String(3), existing_type=sa.String(10), existing_nullable=True)
    with op.batch_alter_table("nota_emitida") as batch:
        batch.alter_column("ctribmun", type_=sa.String(3), existing_type=sa.String(10), existing_nullable=True)
        batch.drop_column("canal")
