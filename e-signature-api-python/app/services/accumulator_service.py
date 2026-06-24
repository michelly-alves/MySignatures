import asyncio
import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accumulator import (
    AccumulatorElement,
    AccumulatorElementState,
    AccumulatorState,
    PublicAccumulatorRegistry,
    Witness,
)
from app.services.rsa_accumulator_adapter import rsa_accumulator_adapter
from app.utils.timing import accumulate_duration, log_duration


logger = logging.getLogger(__name__)

_ACCUMULATOR_TX_LOCK_KEY = 815_042_001


@dataclass(frozen=True)
class AccumulatorRecord:
    state: AccumulatorState
    element: AccumulatorElement
    witness: Witness
    previous_state: AccumulatorState | None = None


def state_fingerprint(state_value_hex: str) -> str:
    """
    Impressão digital canônica de um estado do acumulador: SHA-256 da
    representação hexadecimal minúscula e sem zeros à esquerda (a mesma
    produzida por ``_to_hex``). É o valor curto (64 hex) embutido no selo
    dos PDFs e exposto no registro público — quem possui um, confere o
    outro recalculando o hash.
    """
    return hashlib.sha256(state_value_hex.strip().lower().encode("ascii")).hexdigest()


def hash_to_prime(hash_hex: str) -> int:
    return rsa_accumulator_adapter.backend.hash_to_prime(hash_hex)


def _to_hex(value: int) -> str:
    return format(value, "x")


def _from_hex(value: str) -> int:
    return int(value, 16) 


async def get_latest_state(db: AsyncSession) -> AccumulatorState | None:

    result = await db.execute(
        select(AccumulatorState)
        .order_by(AccumulatorState.state_id.desc())
        .limit(1)
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


async def materialize_witnesses_for_state(
    db: AsyncSession,
    state: AccumulatorState,
    created_by: int | None = None,
) -> dict[int, Witness]:
    """
    Geração SOB DEMANDA e EM LOTE das testemunhas de todos os elementos
    incorporados até ``state``, via RootFactor — O(n log n) exponenciações,
    custo amortizado O(log n) por testemunha (Boneh–Bünz–Fisch 2019, §4.1).

    É o complemento do modo "testemunha sob demanda" adotado pelo sistema:
    a acumulação não atualiza testemunha alguma (O(1)); quem precisa de uma
    prova fresca contra um estado arbitrário (perícia, auditoria) paga o
    lote aqui. O resultado é memoizado na tabela ``witness``: chamadas
    subsequentes para o mesmo estado retornam do banco sem recomputar.
    """
    existing = await db.execute(
        select(Witness).where(Witness.state_id == state.state_id)
    )
    witnesses_by_element_id: dict[int, Witness] = {
        witness.element_id: witness for witness in existing.scalars().all()
    }

    result = await db.execute(
        select(AccumulatorElement)
        .join(
            AccumulatorElementState,
            AccumulatorElementState.element_id == AccumulatorElement.element_id,
        )
        .where(AccumulatorElementState.state_id <= state.state_id)
        .order_by(AccumulatorElement.element_id)
    )
    elements = result.scalars().all()

    if not elements or all(
        element.element_id in witnesses_by_element_id for element in elements
    ):
        return witnesses_by_element_id

    generator = _from_hex(state.generator_hex)
    state_value = _from_hex(state.state_value_hex)
    modulus_n = _from_hex(state.modulus_n_hex)
    x_values = [_from_hex(element.x_value_hex) for element in elements]

    def _compute() -> tuple[list[int], list[bool]]:
        witness_values = rsa_accumulator_adapter.create_membership_witnesses(
            generator=generator,
            elements=x_values,
            modulus_n=modulus_n,
        )
        validities = [
            rsa_accumulator_adapter.verify_membership(
                witness=witness_value,
                element=x_value,
                state_value=state_value,
                modulus_n=modulus_n,
            )
            for witness_value, x_value in zip(witness_values, x_values)
        ]
        return witness_values, validities

    witness_values, validities = await asyncio.to_thread(_compute)

    for element, witness_value, is_valid in zip(elements, witness_values, validities):
        if element.element_id in witnesses_by_element_id:
            continue
        witness = Witness(
            element_id=element.element_id,
            state_id=state.state_id,
            witness_value_hex=_to_hex(witness_value),
            created_by=created_by,
            is_valid=is_valid,
        )
        db.add(witness)
        witnesses_by_element_id[element.element_id] = witness

    await db.flush()
    return witnesses_by_element_id


async def get_witness_on_demand(
    db: AsyncSession,
    element_id: int,
    state_id: int | None = None,
) -> dict | None:
    """
    Testemunha de um elemento contra um estado arbitrário da cadeia (o mais
    recente, se ``state_id`` for None), materializando o lote daquele estado
    se ainda não existir. Retorna None se o estado não existe ou se o
    elemento ainda não havia sido incorporado até ele.
    """
    if state_id is None:
        state = await get_latest_state(db)
    else:
        result = await db.execute(
            select(AccumulatorState).where(AccumulatorState.state_id == state_id)
        )
        state = result.scalars().first()
    if not state:
        return None

    witnesses = await materialize_witnesses_for_state(db, state)
    witness = witnesses.get(element_id)
    if witness is None:
        return None

    element_result = await db.execute(
        select(AccumulatorElement).where(AccumulatorElement.element_id == element_id)
    )
    element = element_result.scalars().first()

    return {
        "element_id": element_id,
        "state_id": state.state_id,
        "state_value_hex": state.state_value_hex,
        "state_sha256": state_fingerprint(state.state_value_hex),
        "modulus_n_hex": state.modulus_n_hex,
        "x_hex": element.x_value_hex,
        "x_nonce": element.x_nonce,
        "witness_hex": witness.witness_value_hex,
        "valid": witness.is_valid,
    }


async def get_single_witness_on_demand(
    db: AsyncSession,
    element_id: int,
    state_id: int | None = None,
) -> dict | None:
    """
    Testemunha de pertencimento de UM elemento contra um estado, calculada
    isoladamente: ``w = g^(produto dos demais x) mod N``.

    É o caminho pericial endurecido: ao contrário de
    ``materialize_witnesses_for_state`` (lote RootFactor, O(n log n) e até n
    inserções), aqui a perícia pede a prova de UMA assinatura, então o custo é
    uma única exponenciação modular e UMA linha inserida — eliminando o vetor
    de amplificação (O(n²) de armazenamento) do endpoint sob demanda.

    Memoizado: se a testemunha (element, state) já existir, retorna do banco.
    Retorna None se o estado/elemento não existe ou se o elemento ainda não
    havia sido incorporado até o estado solicitado.
    """
    if state_id is None:
        state = await get_latest_state(db)
    else:
        result = await db.execute(
            select(AccumulatorState).where(AccumulatorState.state_id == state_id)
        )
        state = result.scalars().first()
    if not state:
        return None

    element_result = await db.execute(
        select(AccumulatorElement).where(AccumulatorElement.element_id == element_id)
    )
    element = element_result.scalars().first()
    if element is None:
        return None

    incorporated = await db.scalar(
        select(func.count())
        .select_from(AccumulatorElementState)
        .where(
            AccumulatorElementState.element_id == element_id,
            AccumulatorElementState.state_id <= state.state_id,
        )
    )
    if not incorporated:
        return None

    existing = await db.execute(
        select(Witness).where(
            Witness.element_id == element_id,
            Witness.state_id == state.state_id,
        )
    )
    witness = existing.scalars().first()

    if witness is not None:
        logger.info(
            "[TEMPO] Testemunha sob Demanda servida do cache (memoizada, ~0 ms) "
            "| element_id=%s | state_id=%s",
            element_id,
            state.state_id,
        )
    else:
        generator = _from_hex(state.generator_hex)
        modulus_n = _from_hex(state.modulus_n_hex)
        state_value = _from_hex(state.state_value_hex)
        x_target = _from_hex(element.x_value_hex)

        others = await db.execute(
            select(AccumulatorElement.x_value_hex)
            .join(
                AccumulatorElementState,
                AccumulatorElementState.element_id == AccumulatorElement.element_id,
            )
            .where(
                AccumulatorElementState.state_id <= state.state_id,
                AccumulatorElement.element_id != element_id,
            )
        )
        other_x_values = [_from_hex(value) for value in others.scalars().all()]

        def _compute() -> tuple[int, bool]:
            exponent = 1
            for value in other_x_values:
                exponent *= value
            witness_value = pow(generator, exponent, modulus_n)
            is_valid = pow(witness_value, x_target, modulus_n) == state_value
            return witness_value, is_valid

        # Mede SÓ a geração da testemunha (witness = g^(produto dos demais x)
        # mod N): a parte cara e O(n) do endpoint /accumulator/witness.
        with log_duration(
            logger,
            "Geração de Testemunha sob Demanda (witness = g^(prod x_i) mod n)",
            element_id=element_id,
            state_id=state.state_id,
            n_outros=len(other_x_values),
        ):
            witness_value, is_valid = await asyncio.to_thread(_compute)

        witness = Witness(
            element_id=element_id,
            state_id=state.state_id,
            witness_value_hex=_to_hex(witness_value),
            is_valid=is_valid,
        )
        db.add(witness)
        await db.flush()

    return {
        "element_id": element_id,
        "state_id": state.state_id,
        "state_value_hex": state.state_value_hex,
        "state_sha256": state_fingerprint(state.state_value_hex),
        "modulus_n_hex": state.modulus_n_hex,
        "x_hex": element.x_value_hex,
        "x_nonce": element.x_nonce,
        "witness_hex": witness.witness_value_hex,
        "valid": witness.is_valid,
    }


async def accumulate_signature(
    db: AsyncSession,
    document_id: int,
    signature_id: int,
    hash_hex: str,
    created_by: int | None = None,
) -> AccumulatorRecord:


    timings: dict[str, float] = {}

    with accumulate_duration(timings, "io_db"):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _ACCUMULATOR_TX_LOCK_KEY},
        )

    with accumulate_duration(timings, "io_db"):
        duplicate = await db.execute(
            select(AccumulatorElement).where(
                (AccumulatorElement.signature_id == signature_id)
                | (AccumulatorElement.hash_hex == hash_hex)
            )
        )
        is_duplicate = duplicate.scalars().first() is not None
    if is_duplicate:
        raise ValueError(
            "Evento de assinatura já acumulado: violaria a unicidade de elementos "
            "do acumulador (signature_id ou hash_hex já registrados)."
        )

    with accumulate_duration(timings, "io_db"):
        current_state = await ensure_initial_state(db, created_by=created_by)

    old_state_value = _from_hex(current_state.state_value_hex)
    modulus_n = _from_hex(current_state.modulus_n_hex)

    with accumulate_duration(timings, "cripto"):
        computation = await asyncio.to_thread(
            rsa_accumulator_adapter.accumulate,
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
    element = AccumulatorElement(
        document_id=document_id,
        signature_id=signature_id,
        hash_hex=hash_hex,
        x_value_hex=_to_hex(computation.x_value),
        x_nonce=computation.x_nonce,
        created_by=created_by,
    )

    db.add_all([state, element])
    with accumulate_duration(timings, "io_db"):
        await db.flush()

    element_state = AccumulatorElementState(
        element_id=element.element_id,
        state_id=state.state_id,
    )
    db.add(element_state)


    witness = Witness(
        element_id=element.element_id,
        state_id=state.state_id,
        witness_value_hex=_to_hex(old_state_value),
        created_by=created_by,
        is_valid=True,
    )
    db.add(witness)

    registry = PublicAccumulatorRegistry(
        state_id=state.state_id,
        source=rsa_accumulator_adapter.backend_name,
    )
    db.add(registry)
    with accumulate_duration(timings, "io_db"):
        await db.flush()

    logger.info(
        "[TEMPO] Acumulação (detalhe, modo sob demanda) | cripto=%.2f ms | "
        "io_db=%.2f ms | document_id=%s | signature_id=%s",
        timings.get("cripto", 0.0),
        timings.get("io_db", 0.0),
        document_id,
        signature_id,
    )

    return AccumulatorRecord(
        state=state,
        element=element,
        witness=witness,
        previous_state=current_state,
    )


async def get_public_registry_page(
    db: AsyncSession,
    after_state_id: int = 0,
    limit: int = 100,
) -> list[tuple[AccumulatorState, object, str | None]]:
    """
    Página do registro público de estados, em ordem crescente de state_id
    (paginação por keyset via ``after_state_id``, pensada para espelhamento
    incremental por verificadores externos).

    Cada linha traz o estado, o ``published_at`` do registro e o ``x`` do
    elemento incorporado naquela transição (None para o estado inicial),
    permitindo verificar cada elo: pow(S_anterior, x, N) == S.
    """
    result = await db.execute(
        select(
            AccumulatorState,
            PublicAccumulatorRegistry.published_at,
            AccumulatorElement.x_value_hex,
        )
        .join(
            PublicAccumulatorRegistry,
            PublicAccumulatorRegistry.state_id == AccumulatorState.state_id,
        )
        .outerjoin(
            AccumulatorElementState,
            AccumulatorElementState.state_id == AccumulatorState.state_id,
        )
        .outerjoin(
            AccumulatorElement,
            AccumulatorElement.element_id == AccumulatorElementState.element_id,
        )
        .where(AccumulatorState.state_id > after_state_id)
        .order_by(AccumulatorState.state_id)
        .limit(limit)
    )
    return result.all()


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
