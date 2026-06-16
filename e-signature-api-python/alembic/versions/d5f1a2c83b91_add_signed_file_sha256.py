"""add_signed_file_sha256_to_digital_signature

Revision ID: d5f1a2c83b91
Revises: c3a7e51d9b02
Create Date: 2026-06-14 20:40:00.000000

Armazena o SHA-256 do PDF SELADO (entregue ao usuário) para permitir a
verificação de integridade pós-assinatura do documento final, distinta da
verificação do PDF original (cujo hash já está em document.hash_sha256).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f1a2c83b91'
down_revision: Union[str, Sequence[str], None] = 'c3a7e51d9b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'digital_signature',
        sa.Column('signed_file_sha256', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('digital_signature', 'signed_file_sha256')
