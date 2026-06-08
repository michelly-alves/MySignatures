"""fix company

Revision ID: db090b412674
Revises: 2f9814fca9f1
Create Date: 2026-01-03 21:22:52.163162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'db090b412674'
down_revision: Union[str, Sequence[str], None] = '2f9814fca9f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "company",
        "contact_email",
        new_column_name="email",
        existing_type=sa.String(),
        nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "company",
        "email",
        new_column_name="contact_email",
        existing_type=sa.String(),
        nullable=False
    )

    # ### end Alembic commands ###
