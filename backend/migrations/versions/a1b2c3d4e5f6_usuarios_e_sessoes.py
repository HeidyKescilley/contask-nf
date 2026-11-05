"""usuários e sessões de login

Revision ID: a1b2c3d4e5f6
Revises: f0cd4aedb5ea
Create Date: 2026-11-05 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f0cd4aedb5ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usuario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('nome', sa.String(length=200), nullable=False),
        sa.Column('senha_hash', sa.String(length=300), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('trocar_senha', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ultimo_acesso_em', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'sessao_usuario',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    with op.batch_alter_table('sessao_usuario') as b:
        b.create_index('ix_sessao_usuario_usuario_id', ['usuario_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sessao_usuario') as b:
        b.drop_index('ix_sessao_usuario_usuario_id')
    op.drop_table('sessao_usuario')
    op.drop_table('usuario')
