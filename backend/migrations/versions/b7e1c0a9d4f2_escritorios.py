"""escritórios no mesmo banco

Revision ID: b7e1c0a9d4f2
Revises: a1b2c3d4e5f6
Create Date: 2026-11-05 16:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e1c0a9d4f2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# O unique antigo foi criado sem nome. O batch do SQLite só consegue removê-lo
# depois que a convenção dá um nome ao que a reflexão devolveu sem nome.
_UQ = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    op.create_table(
        "escritorio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for tabela in ("empresa", "certificado", "usuario"):
        with op.batch_alter_table(tabela) as batch:
            batch.add_column(sa.Column("escritorio_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    tem = any(
        conn.execute(sa.text(f"SELECT COUNT(*) FROM {tabela}")).scalar()
        for tabela in ("empresa", "certificado", "usuario")
    )
    if tem:
        conn.execute(sa.text("INSERT INTO escritorio (nome) VALUES ('Escritório')"))
        eid = conn.execute(sa.text("SELECT id FROM escritorio ORDER BY id LIMIT 1")).scalar()
        for tabela in ("empresa", "certificado", "usuario"):
            conn.execute(sa.text(f"UPDATE {tabela} SET escritorio_id = :e WHERE escritorio_id IS NULL"), {"e": eid})

    with op.batch_alter_table("empresa", naming_convention=_UQ) as batch:
        batch.drop_constraint("uq_empresa_cnpj", type_="unique")
        batch.drop_index("ux_empresa_contabilidade")
        batch.alter_column("escritorio_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_empresa_escritorio_id", "escritorio", ["escritorio_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_empresa_escritorio_id", ["escritorio_id"], unique=False)
        batch.create_unique_constraint("uq_empresa_escritorio_cnpj", ["escritorio_id", "cnpj"])
        batch.create_index(
            "ux_empresa_contabilidade", ["escritorio_id"], unique=True,
            sqlite_where=sa.text("is_contabilidade = 1"),
        )
    with op.batch_alter_table("certificado", naming_convention=_UQ) as batch:
        batch.drop_constraint("uq_certificado_thumbprint", type_="unique")
        batch.alter_column("escritorio_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_certificado_escritorio_id", "escritorio", ["escritorio_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_certificado_escritorio_id", ["escritorio_id"], unique=False)
        batch.create_unique_constraint("uq_certificado_escritorio_thumbprint", ["escritorio_id", "thumbprint"])
    with op.batch_alter_table("usuario") as batch:
        batch.alter_column("escritorio_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_usuario_escritorio_id", "escritorio", ["escritorio_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_usuario_escritorio_id", ["escritorio_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.drop_index("ix_usuario_escritorio_id")
        batch.drop_constraint("fk_usuario_escritorio_id", type_="foreignkey")
        batch.drop_column("escritorio_id")
    with op.batch_alter_table("certificado") as batch:
        batch.drop_constraint("uq_certificado_escritorio_thumbprint", type_="unique")
        batch.drop_index("ix_certificado_escritorio_id")
        batch.drop_constraint("fk_certificado_escritorio_id", type_="foreignkey")
        batch.drop_column("escritorio_id")
        batch.create_unique_constraint("uq_certificado_thumbprint", ["thumbprint"])
    with op.batch_alter_table("empresa") as batch:
        batch.drop_index("ux_empresa_contabilidade", sqlite_where=sa.text("is_contabilidade = 1"))
        batch.drop_constraint("uq_empresa_escritorio_cnpj", type_="unique")
        batch.drop_index("ix_empresa_escritorio_id")
        batch.drop_constraint("fk_empresa_escritorio_id", type_="foreignkey")
        batch.drop_column("escritorio_id")
        batch.create_unique_constraint("uq_empresa_cnpj", ["cnpj"])
        batch.create_index(
            "ux_empresa_contabilidade", ["is_contabilidade"], unique=True,
            sqlite_where=sa.text("is_contabilidade = 1"),
        )
    op.drop_table("escritorio")
