"""tomador no exterior (NIF, país, endereço) e comércio exterior da nota

Revision ID: e6a8c0d2f4b5
Revises: d5f7b9c1e3a4
Create Date: 2026-11-24 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6a8c0d2f4b5"
down_revision: Union[str, Sequence[str], None] = "d5f7b9c1e3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS = (("pais", 2), ("nif", 40), ("nao_nif", 1), ("cod_postal", 11), ("cidade", 60), ("estado_provincia", 60))


def upgrade() -> None:
    with op.batch_alter_table("tomador") as b:
        # tomador no exterior: o documento guarda uma chave própria (EX + país + NIF ou nome), até 40
        b.alter_column("documento", type_=sa.String(40), existing_type=sa.String(14))
        for nome, tam in COLUNAS:
            b.add_column(sa.Column(nome, sa.String(tam), nullable=True))
    with op.batch_alter_table("nota_emitida") as b:
        b.add_column(sa.Column("comercio_exterior", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("nota_emitida") as b:
        b.drop_column("comercio_exterior")
    with op.batch_alter_table("tomador") as b:
        for nome, _ in reversed(COLUNAS):
            b.drop_column(nome)
        b.alter_column("documento", type_=sa.String(14), existing_type=sa.String(40))
