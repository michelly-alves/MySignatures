"""accumulator base derivation counter and record hash chain

Adiciona ao acumulador RSA dois parâmetros estruturais:

1. ``accumulator_state.base_counter`` — contador público da derivação
   determinística da base ``g = h² mod N`` (h via SHA-256 com separação de
   domínio ligada a N). Substitui a antiga base sorteada aleatoriamente,
   permitindo que um verificador externo reproduza g.

2. ``accumulator_state.record_hash`` — encadeamento por hash dos registros de
   estado (record_hash = H(dominio ‖ hash do registro anterior ‖ valor do
   estado ‖ x incluído ‖ N ‖ g)), tornando a cadeia tamper-evident.

Ambas as colunas são nullable para compatibilidade com estados criados antes
desta revisão (g aleatório, sem encadeamento). Novos estados sempre as
preenchem.

Revision ID: c2d7f3a9b104
Revises: e7b2a9c41d05
Create Date: 2026-06-24 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d7f3a9b104"
down_revision: Union[str, Sequence[str], None] = "e7b2a9c41d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accumulator_state",
        sa.Column("base_counter", sa.Integer(), nullable=True),
    )
    op.add_column(
        "accumulator_state",
        sa.Column("record_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accumulator_state", "record_hash")
    op.drop_column("accumulator_state", "base_counter")
