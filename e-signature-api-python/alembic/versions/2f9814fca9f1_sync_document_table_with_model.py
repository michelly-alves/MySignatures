"""sync document table with model

Revision ID: 2f9814fca9f1
Revises: 3426de3d4e46
Create Date: 2026-01-03 18:01:37.917261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f9814fca9f1'
down_revision: Union[str, Sequence[str], None] = '3426de3d4e46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "document",
        sa.Column("file_name", sa.String(), nullable=True)
    )
    op.add_column(
        "document",
        sa.Column("file_path", sa.String(), nullable=True)
    )
    op.add_column(
        "document",
        sa.Column("status_id", sa.Integer(), nullable=True)
    )

def downgrade() -> None:
    """Downgrade schema."""
    pass
