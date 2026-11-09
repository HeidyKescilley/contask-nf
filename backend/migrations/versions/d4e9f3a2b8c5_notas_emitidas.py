"""emissor: notas emitidas, município e percentual de tributos do prestador

Revision ID: d4e9f3a2b8c5
Revises: c3d8e2f1a7b4
Create Date: 2026-11-09 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e9f3a2b8c5"
down_revision: Union[str, Sequence[str], None] = "c3d8e2f1a7b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D = sa.Numeric(precision=15, scale=2)


def upgrade() -> None:
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.add_column(sa.Column("cod_municipio", sa.String(length=7), nullable=True))
        batch.add_column(sa.Column("percentual_tributos", sa.Numeric(precision=5, scale=2), nullable=True))

    op.create_table(
        "nota_emitida",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("servico_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("ambiente", sa.Integer(), nullable=False),
        sa.Column("serie", sa.String(length=5), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("id_dps", sa.String(length=45), nullable=False),
        sa.Column("situacao", sa.String(length=12), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("tomador", sa.JSON(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("ctribnac", sa.String(length=6), nullable=False),
        sa.Column("cnbs", sa.String(length=9), nullable=False),
        sa.Column("ctribmun", sa.String(length=3), nullable=True),
        sa.Column("cod_municipio_prestacao", sa.String(length=7), nullable=False),
        sa.Column("valor_servico", _D, nullable=False),
        sa.Column("desconto", _D, nullable=False),
        sa.Column("iss_retido", sa.Boolean(), nullable=False),
        sa.Column("aliquota_iss", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("ret_pis", _D, nullable=False),
        sa.Column("ret_cofins", _D, nullable=False),
        sa.Column("ret_csll", _D, nullable=False),
        sa.Column("ret_irrf", _D, nullable=False),
        sa.Column("ret_cp", _D, nullable=False),
        sa.Column("info_complementar", sa.Text(), nullable=True),
        sa.Column("chave", sa.String(length=50), nullable=True),
        sa.Column("numero_nfse", sa.String(length=20), nullable=True),
        sa.Column("valor_iss", _D, nullable=True),
        sa.Column("valor_liquido", _D, nullable=True),
        sa.Column("erros", sa.JSON(), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("xml_dps_path", sa.String(length=500), nullable=True),
        sa.Column("xml_nfse_path", sa.String(length=500), nullable=True),
        sa.Column("xml_cancelamento_path", sa.String(length=500), nullable=True),
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("autorizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorio.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresa.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["servico_id"], ["servico_emissor.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ambiente", "id_dps", name="uq_nota_emitida_ambiente_id_dps"),
    )
    op.create_index("ix_nota_emitida_escritorio_id", "nota_emitida", ["escritorio_id"])
    op.create_index("ix_nota_emitida_empresa_id", "nota_emitida", ["empresa_id"])
    op.create_index("ix_nota_emitida_situacao", "nota_emitida", ["situacao"])
    op.create_index("ix_nota_emitida_chave", "nota_emitida", ["chave"])


def downgrade() -> None:
    for ix in ("chave", "situacao", "empresa_id", "escritorio_id"):
        op.drop_index(f"ix_nota_emitida_{ix}", table_name="nota_emitida")
    op.drop_table("nota_emitida")
    with op.batch_alter_table("emissor_empresa") as batch:
        batch.drop_column("percentual_tributos")
        batch.drop_column("cod_municipio")
