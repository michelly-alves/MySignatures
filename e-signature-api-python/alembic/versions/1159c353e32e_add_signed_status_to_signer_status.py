"""add_signed_status_to_signer_status

Revision ID: 1159c353e32e
Revises: 70e4e9058181
Create Date: 2026-05-27 21:06:47.162764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1159c353e32e'
down_revision: Union[str, Sequence[str], None] = '70e4e9058181'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT INTO signer_status (status_id, name) VALUES (4, 'SIGNED') ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM signer_status WHERE status_id = 4")
