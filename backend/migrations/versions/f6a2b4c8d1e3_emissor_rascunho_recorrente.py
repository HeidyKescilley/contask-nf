"""emissor: regime tributário, rascunhos e notas recorrentes

Revision ID: f6a2b4c8d1e3
Revises: e5f1a3b7c9d2
Create Date: 2026-11-09 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a2b4c8d1e3"
down_revision: Union[str, Sequence[str], None] = "e5f1a3b7c9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.add_column(sa.Column("regime_tributario", sa.String(10), nullable=True))
    op.execute("UPDATE emissor_empresa SET regime_tributario = 'simples' WHERE op_simples IN ('2', '3')")

    op.create_table(
        "nota_rascunho",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dados", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_nota_rascunho_escritorio_id", "nota_rascunho", ["escritorio_id"])
    op.create_index("ix_nota_rascunho_empresa_id", "nota_rascunho", ["empresa_id"])

    op.create_table(
        "nota_recorrente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("escritorio_id", sa.Integer(), sa.ForeignKey("escritorio.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=False),
        sa.Column("dia", sa.Integer(), nullable=False),
        sa.Column("competencia", sa.String(8), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("proxima_em", sa.Date(), nullable=True),
        sa.Column("ultima_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_nota_id", sa.Integer(), sa.ForeignKey("nota_emitida.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_nota_recorrente_escritorio_id", "nota_recorrente", ["escritorio_id"])
    op.create_index("ix_nota_recorrente_empresa_id", "nota_recorrente", ["empresa_id"])
    op.create_index("ix_nota_recorrente_proxima_em", "nota_recorrente", ["proxima_em"])

    with op.batch_alter_table("nota_emitida") as batch:
        batch.add_column(sa.Column("recorrente_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_nota_emitida_recorrente", "nota_recorrente", ["recorrente_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("nota_emitida") as batch:
        batch.drop_constraint("fk_nota_emitida_recorrente", type_="foreignkey")
        batch.drop_column("recorrente_id")
    op.drop_table("nota_recorrente")
    op.drop_table("nota_rascunho")
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.drop_column("regime_tributario")
