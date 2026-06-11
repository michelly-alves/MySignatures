"""accumulator performance and serialization

Correções de desempenho e serialização do acumulador RSA:

1. Índice único parcial em ``accumulator_state.previous_state_id`` (não
   nulo): impede a bifurcação da cadeia de estados quando duas acumulações
   concorrentes partem do mesmo estado — duas linhas com o mesmo
   ``previous_state_id`` significariam dois sucessores para o mesmo estado.
   Complementa (defesa em profundidade) o advisory lock transacional tomado
   em ``accumulate_signature``.

2. Índices em ``witness(state_id)`` e ``witness(element_id)``: a atualização
   incremental filtra por ``state_id`` e as consultas de prova fazem join
   por ``element_id``; sem índice (PostgreSQL não indexa FKs
   automaticamente), cada acumulação degenerava em full scan.

3. Poda de testemunhas históricas: o serviço passa a manter apenas as
   testemunhas do estado mais recente (as provas sempre usam a mais
   recente). Esta migration remove as testemunhas de estados anteriores já
   acumuladas, que cresciam O(n²).

Revision ID: c3a7e51d9b02
Revises: b1f4c92e6a8d
Create Date: 2026-06-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3a7e51d9b02"
down_revision: Union[str, Sequence[str], None] = "b1f4c92e6a8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accumulator_state_previous
        ON accumulator_state (previous_state_id)
        WHERE previous_state_id IS NOT NULL;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_witness_state_id ON witness (state_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_witness_element_id ON witness (element_id);")

    op.execute(
        """
        DELETE FROM witness
        WHERE state_id <> (SELECT MAX(state_id) FROM accumulator_state);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_witness_element_id;")
    op.execute("DROP INDEX IF EXISTS ix_witness_state_id;")
    op.execute("DROP INDEX IF EXISTS uq_accumulator_state_previous;")
