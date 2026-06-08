"""improve rsa accumulator witnesses

Revision ID: a7c4d8e91f23
Revises: db090b412674
Create Date: 2026-04-22 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c4d8e91f23"
down_revision: Union[str, Sequence[str], None] = "db090b412674"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accumulator_element",
        sa.Column("x_nonce", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("accumulator_element", "x_nonce", server_default=None)

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'witness_element_id_key'
            ) THEN
                ALTER TABLE witness DROP CONSTRAINT witness_element_id_key;
            END IF;
        END
        $$;
        """
    )

    op.create_index(
        "idx_witness_element_state",
        "witness",
        ["element_id", "state_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_witness_element_state", table_name="witness")
    op.drop_column("accumulator_element", "x_nonce")
