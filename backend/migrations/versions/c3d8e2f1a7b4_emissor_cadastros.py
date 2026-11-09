"""emissor: empresas emissoras, serviços e tomadores

Revision ID: c3d8e2f1a7b4
Revises: b7e1c0a9d4f2
Create Date: 2026-11-09 07:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d8e2f1a7b4"
down_revision: Union[str, Sequence[str], None] = "b7e1c0a9d4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("empresa") as batch:
        batch.add_column(sa.Column("emite_nfse", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "emissor_empresa",
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("inscricao_municipal", sa.String(length=15), nullable=True),
        sa.Column("op_simples", sa.String(length=1), nullable=False),
        sa.Column("reg_ap_trib_sn", sa.String(length=1), nullable=True),
        sa.Column("reg_esp_trib", sa.String(length=1), nullable=False),
        sa.Column("serie", sa.String(length=5), nullable=False),
        sa.Column("proximo_numero", sa.Integer(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresa.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("empresa_id"),
    )
    op.create_table(
        "servico_emissor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("ctribnac", sa.String(length=6), nullable=False),
        sa.Column("cnbs", sa.String(length=9), nullable=False),
        sa.Column("ctribmun", sa.String(length=3), nullable=True),
        sa.Column("cindop", sa.String(length=6), nullable=True),
        sa.Column("cclasstrib", sa.String(length=6), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresa.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_servico_emissor_empresa_id", "servico_emissor", ["empresa_id"])
    op.create_table(
        "tomador",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("documento", sa.String(length=14), nullable=False),
        sa.Column("nome", sa.String(length=300), nullable=False),
        sa.Column("inscricao_municipal", sa.String(length=15), nullable=True),
        sa.Column("cep", sa.String(length=8), nullable=True),
        sa.Column("cod_municipio", sa.String(length=7), nullable=True),
        sa.Column("municipio", sa.String(length=100), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("logradouro", sa.String(length=255), nullable=True),
        sa.Column("numero", sa.String(length=60), nullable=True),
        sa.Column("complemento", sa.String(length=156), nullable=True),
        sa.Column("bairro", sa.String(length=60), nullable=True),
        sa.Column("telefone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=80), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escritorio_id", "documento", name="uq_tomador_escritorio_documento"),
    )
    op.create_index("ix_tomador_escritorio_id", "tomador", ["escritorio_id"])


def downgrade() -> None:
    op.drop_index("ix_tomador_escritorio_id", table_name="tomador")
    op.drop_table("tomador")
    op.drop_index("ix_servico_emissor_empresa_id", table_name="servico_emissor")
    op.drop_table("servico_emissor")
    op.drop_table("emissor_empresa")
    with op.batch_alter_table("empresa") as batch:
        batch.drop_column("emite_nfse")
