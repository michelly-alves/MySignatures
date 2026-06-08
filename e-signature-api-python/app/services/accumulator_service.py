from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accumulator import (
    AccumulatorElement,
    AccumulatorElementState,
    AccumulatorState,
    PublicAccumulatorRegistry,
    Witness,
)
from app.services.rsa_accumulator_adapter import rsa_accumulator_adapter

@dataclass(frozen=True)
class AccumulatorRecord:
    state: AccumulatorState
    element: AccumulatorElement
    witness: Witness


def hash_to_prime(hash_hex: str) -> int:
    return rsa_accumulator_adapter.backend.hash_to_prime(hash_hex)


def _to_hex(value: int) -> str:
    return format(value, "x")


def _from_hex(value: str) -> int:
    return int(value, 16) 


async def get_latest_state(db: AsyncSession) -> AccumulatorState | None:
    result = await db.execute(
        select(AccumulatorState).order_by(AccumulatorState.state_id.desc())
    )
    return result.scalars().first()


async def ensure_initial_state(
    db: AsyncSession,
    created_by: int | None = None,
) -> AccumulatorState:
    state = await get_latest_state(db)
    if state:
        return state

    generator, modulus_n = rsa_accumulator_adapter.generate_initial_parameters()

    state = AccumulatorState(
        previous_state_id=None,
        state_value_hex=_to_hex(generator),
        generator_hex=_to_hex(generator),
        modulus_n_hex=_to_hex(modulus_n),
        created_by=created_by,
        comments=f"Estado inicial do acumulador RSA ({rsa_accumulator_adapter.backend_name})",
    )
    db.add(state)
    await db.flush()

    registry = PublicAccumulatorRegistry(
        state_id=state.state_id,
        source=rsa_accumulator_adapter.backend_name,
    )
    db.add(registry)
    await db.flush()
    return state


async def _update_witnesses_incrementally(
    db: AsyncSession,
    old_state: AccumulatorState,
    new_state: AccumulatorState,
    new_element: AccumulatorElement,
    new_x_value: int,
    old_state_value: int,
    created_by: int | None = None,
) -> dict[int, Witness]:
    """
    Atualiza testemunhas em O(n) por assinatura.

    Princípio:
      Seja S = g^(e1·…·en) o estado ANTERIOR e S' = g^(e1·…·en·e_new) o NOVO estado.

      Para cada elemento existente ei com testemunha w_i (válida para S):
        w_i' = pow(w_i, e_new, N)
        pow(w_i', ei, N) = pow(g^(Π_{j≠i} ej · e_new), ei, N) = S'  ✓

      Para o novo elemento e_new:
        w_new = old_state_value = g^(e1·…·en)
        pow(w_new, e_new, N) = g^(e1·…·en·e_new) = S'  ✓
    """
    modulus_n = _from_hex(new_state.modulus_n_hex)
    new_state_value = _from_hex(new_state.state_value_hex)

    result = await db.execute(
        select(Witness, AccumulatorElement)
        .join(AccumulatorElement, AccumulatorElement.element_id == Witness.element_id)
        .where(Witness.state_id == old_state.state_id)
    )
    rows = result.all()

    witnesses_by_element_id: dict[int, Witness] = {}

    for old_witness, element in rows:
        old_w = _from_hex(old_witness.witness_value_hex)
        new_w_value = pow(old_w, new_x_value, modulus_n)
        x_value = _from_hex(element.x_value_hex)

        witness = Witness(
            element_id=element.element_id,
            state_id=new_state.state_id,
            witness_value_hex=_to_hex(new_w_value),
            created_by=created_by,
            is_valid=pow(new_w_value, x_value, modulus_n) == new_state_value,
        )
        db.add(witness)
        witnesses_by_element_id[element.element_id] = witness

    new_element_witness = Witness(
        element_id=new_element.element_id,
        state_id=new_state.state_id,
        witness_value_hex=_to_hex(old_state_value),
        created_by=created_by,
        is_valid=pow(old_state_value, new_x_value, modulus_n) == new_state_value,
    )
    db.add(new_element_witness)
    witnesses_by_element_id[new_element.element_id] = new_element_witness

    await db.flush()
    return witnesses_by_element_id


async def _recompute_all_witnesses(
    db: AsyncSession,
    state: AccumulatorState,
    created_by: int | None = None,
) -> dict[int, Witness]:
    """
    Recomputa testemunhas do zero para TODOS os elementos — O(n log n).
    Use apenas para recuperação/auditoria quando testemunhas anteriores
    não estiverem disponíveis no banco.
    """
    result = await db.execute(
        select(AccumulatorElement).order_by(AccumulatorElement.element_id)
    )
    elements = result.scalars().all()
    if not elements:
        return {}

    generator = _from_hex(state.generator_hex)
    state_value = _from_hex(state.state_value_hex)
    modulus_n = _from_hex(state.modulus_n_hex)
    x_values = [_from_hex(element.x_value_hex) for element in elements]
    witness_values = rsa_accumulator_adapter.create_membership_witnesses(
        generator=generator,
        elements=x_values,
        modulus_n=modulus_n,
    )

    witnesses_by_element_id: dict[int, Witness] = {}
    for element, x_value, witness_value in zip(elements, x_values, witness_values):
        witness = Witness(
            element_id=element.element_id,
            state_id=state.state_id,
            witness_value_hex=_to_hex(witness_value),
            created_by=created_by,
            is_valid=rsa_accumulator_adapter.verify_membership(
                witness=witness_value,
                element=x_value,
                state_value=state_value,
                modulus_n=modulus_n,
            ),
        )
        db.add(witness)
        witnesses_by_element_id[element.element_id] = witness

    await db.flush()
    return witnesses_by_element_id


async def accumulate_signature(
    db: AsyncSession,
    document_id: int,
    signature_id: int,
    hash_hex: str,
    created_by: int | None = None,
) -> AccumulatorRecord:

    duplicate = await db.execute(
        select(AccumulatorElement).where(
            (AccumulatorElement.signature_id == signature_id)
            | (AccumulatorElement.hash_hex == hash_hex)
        )
    )
    if duplicate.scalars().first() is not None:
        raise ValueError(
            "Evento de assinatura já acumulado: violaria a unicidade de elementos "
            "do acumulador (signature_id ou hash_hex já registrados)."
        )

    current_state = await ensure_initial_state(db, created_by=created_by)

    old_state_value = _from_hex(current_state.state_value_hex)
    modulus_n = _from_hex(current_state.modulus_n_hex)

    computation = rsa_accumulator_adapter.accumulate(
        current_value=old_state_value,
        hash_hex=hash_hex,
        modulus_n=modulus_n,
    )

    state = AccumulatorState(
        previous_state_id=current_state.state_id,
        state_value_hex=_to_hex(computation.new_value),
        generator_hex=current_state.generator_hex,
        modulus_n_hex=current_state.modulus_n_hex,
        created_by=created_by,
        comments=(
            f"Documento {document_id} assinado e acumulado "
            f"({rsa_accumulator_adapter.backend_name})"
        ),
    )
    db.add(state)
    await db.flush()

    element = AccumulatorElement(
        document_id=document_id,
        signature_id=signature_id,
        hash_hex=hash_hex,
        x_value_hex=_to_hex(computation.x_value),
        x_nonce=computation.x_nonce,
        created_by=created_by,
    )
    db.add(element)
    await db.flush()

    element_state = AccumulatorElementState(
        element_id=element.element_id,
        state_id=state.state_id,
    )
    db.add(element_state)

    witnesses = await _update_witnesses_incrementally(
        db=db,
        old_state=current_state,
        new_state=state,
        new_element=element,
        new_x_value=computation.x_value,
        old_state_value=old_state_value,
        created_by=created_by,
    )
    witness = witnesses[element.element_id]

    registry = PublicAccumulatorRegistry(
        state_id=state.state_id,
        source=rsa_accumulator_adapter.backend_name,
    )
    db.add(registry)
    await db.flush()

    return AccumulatorRecord(state=state, element=element, witness=witness)


def verify_membership(witness_hex: str, x_value_hex: str, state_value_hex: str, modulus_n_hex: str) -> bool:
    witness_value = _from_hex(witness_hex)
    x_value = _from_hex(x_value_hex)
    state_value = _from_hex(state_value_hex)
    modulus_n = _from_hex(modulus_n_hex)

    return rsa_accumulator_adapter.verify_membership(
        witness=witness_value,
        element=x_value,
        state_value=state_value,
        modulus_n=modulus_n,
    )
