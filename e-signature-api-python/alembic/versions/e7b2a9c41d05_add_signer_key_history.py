"""add_signer_key_history

Revision ID: e7b2a9c41d05
Revises: d5f1a2c83b91
Create Date: 2026-06-15 10:00:00.000000

Tabela de histórico/revogação de chaves públicas do signatário, usada pelo
fluxo de rotação de chave (perda do .ekey ou da senha).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b2a9c41d05'
down_revision: Union[str, Sequence[str], None] = 'd5f1a2c83b91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'signer_key_history',
        sa.Column('history_id', sa.Integer(), nullable=False),
        sa.Column('signer_id', sa.Integer(), nullable=False),
        sa.Column('public_key', sa.String(), nullable=False),
        sa.Column(
            'revoked_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('revoked_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['signer_id'], ['signer.signer_id']),
        sa.PrimaryKeyConstraint('history_id'),
    )
    op.create_index(
        op.f('ix_signer_key_history_signer_id'),
        'signer_key_history',
        ['signer_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_signer_key_history_signer_id'),
        table_name='signer_key_history',
    )
    op.drop_table('signer_key_history')
