"""accumulator integrity constraints

Adiciona garantias estruturais ao acumulador RSA:

1. Índice único parcial em ``accumulator_state`` que impede a existência
   de mais de uma linha com ``previous_state_id IS NULL``, prevenindo a
   condição de corrida em ``ensure_initial_state`` onde duas requisições
   concorrentes poderiam criar estados iniciais paralelos.

2. Constraint única em ``accumulator_element.signature_id``, reforçando
   no banco a invariante de unicidade verificada no serviço
   ``accumulate_signature`` — defesa em profundidade.

3. Constraint única em ``accumulator_element.hash_hex``, prevenindo
   acumulação do mesmo elemento duas vezes (quebraria a equação de
   testemunha do esquema Baric-Pfitzmann).

Revision ID: b1f4c92e6a8d
Revises: 1159c353e32e
Create Date: 2026-06-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1f4c92e6a8d"
down_revision: Union[str, Sequence[str], None] = "1159c353e32e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Índice único parcial: no máximo uma linha com previous_state_id IS NULL.
    #    Usa expressão booleana (sempre TRUE quando o WHERE bate) para forçar
    #    unicidade em PostgreSQL, que por padrão trata NULL como distinto.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accumulator_state_initial
        ON accumulator_state ((previous_state_id IS NULL))
        WHERE previous_state_id IS NULL;
        """
    )

    # 2. Unicidade da signature_id no acumulador (defesa em profundidade).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accumulator_element_signature_id
        ON accumulator_element (signature_id)
        WHERE signature_id IS NOT NULL;
        """
    )

    # 3. Unicidade do hash_hex: cada evento de assinatura mapeia para um
    #    único primo no acumulador.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accumulator_element_hash_hex
        ON accumulator_element (hash_hex);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_accumulator_element_hash_hex;")
    op.execute("DROP INDEX IF EXISTS uq_accumulator_element_signature_id;")
    op.execute("DROP INDEX IF EXISTS uq_accumulator_state_initial;")
