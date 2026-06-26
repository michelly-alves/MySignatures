import asyncio
import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accumulator import (
    AccumulatorElement,
    AccumulatorElementState,
    AccumulatorState,
    PublicAccumulatorRegistry,
    Witness,
)
from app.services.rsa_accumulator_adapter import rsa_accumulator_adapter
from app.utils.timing import accumulate_duration


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


RECORD_CHAIN_DOMAIN = "ACCUMULATOR-STATE-CHAIN-V1"
GENESIS_PREV_HASH = "0" * 64


def compute_record_hash(
    prev_record_hash: str,
    state_value_hex: str,
    x_value_hex: str,
    modulus_n_hex: str,
    generator_hex: str,
) -> str:
    """
    Hash encadeado de um registro de estado do acumulador. Liga cada estado ao
    anterior por meio de ``prev_record_hash``, tornando a cadeia
    tamper-evident: alterar um estado histórico (ou o representante que o
    produziu) muda este ``record_hash`` e, por propagação, todos os
    posteriores. A serialização é canônica e não ambígua (cada campo prefixado
    pelo seu comprimento em 4 bytes big-endian). O estado inicial usa
    ``prev_record_hash = GENESIS_PREV_HASH`` e ``x_value_hex`` vazio.
    """
    fields = [
        ("dominio", RECORD_CHAIN_DOMAIN),
        ("hash_registro_anterior", prev_record_hash),
        ("valor_estado", state_value_hex),
        ("representante_x", x_value_hex),
        ("modulo_n", modulus_n_hex),
        ("base_g", generator_hex),
    ]
    payload = bytearray()
    for name, value in fields:
        name_bytes = name.encode("utf-8")
        value_bytes = value.encode("utf-8")
        payload += len(name_bytes).to_bytes(4, "big") + name_bytes
        payload += len(value_bytes).to_bytes(4, "big") + value_bytes
    return hashlib.sha256(bytes(payload)).hexdigest()


def hash_to_prime(hash_hex: str) -> int:
    return rsa_accumulator_adapter.backend.hash_to_prime(hash_hex)


def _derive_unused_prime(hash_hex: str, used_x_hex: set[str]) -> tuple[int, int]:
    """
    Deriva o representante primo do evento via hash-to-prime, incrementando o
    contador (nonce) até obter um primo AINDA NÃO utilizado no acumulador.

    Trata explicitamente a colisão — computacionalmente improvável — de
    representantes do esquema Baric-Pfitzmann: dois eventos distintos que
    mapeassem para o mesmo primo quebrariam a equação de testemunha. Retorna
    ``(x, nonce)``, em que ``nonce`` é o contador publicado que reproduz o
    primo escolhido.
    """
    nonce = 0
    while True:
        result = rsa_accumulator_adapter.backend.hash_to_prime_with_nonce(hash_hex, nonce)
        if _to_hex(result.prime) not in used_x_hex:
            return result.prime, result.nonce
        nonce = result.nonce + 1


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

    generator, modulus_n, base_counter = rsa_accumulator_adapter.generate_initial_parameters()

    generator_hex = _to_hex(generator)
    modulus_n_hex = _to_hex(modulus_n)
    state = AccumulatorState(
        previous_state_id=None,
        state_value_hex=generator_hex,
        generator_hex=generator_hex,
        modulus_n_hex=modulus_n_hex,
        base_counter=base_counter,
        record_hash=compute_record_hash(
            prev_record_hash=GENESIS_PREV_HASH,
            state_value_hex=generator_hex,
            x_value_hex="",
            modulus_n_hex=modulus_n_hex,
            generator_hex=generator_hex,
        ),
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

    with accumulate_duration(timings, "io_db"):
        used_x_result = await db.execute(select(AccumulatorElement.x_value_hex))
        used_x_hex = set(used_x_result.scalars().all())

    def _compute() -> tuple[int, int, int]:
        x_value, x_nonce = _derive_unused_prime(hash_hex, used_x_hex)
        new_value = rsa_accumulator_adapter.backend.add(
            old_state_value, x_value, modulus_n
        )
        return x_value, x_nonce, new_value

    with accumulate_duration(timings, "cripto"):
        x_value, x_nonce, new_value = await asyncio.to_thread(_compute)

    new_state_value_hex = _to_hex(new_value)
    x_value_hex = _to_hex(x_value)
    state = AccumulatorState(
        previous_state_id=current_state.state_id,
        state_value_hex=new_state_value_hex,
        generator_hex=current_state.generator_hex,
        modulus_n_hex=current_state.modulus_n_hex,
        base_counter=current_state.base_counter,
        record_hash=compute_record_hash(
            prev_record_hash=current_state.record_hash or GENESIS_PREV_HASH,
            state_value_hex=new_state_value_hex,
            x_value_hex=x_value_hex,
            modulus_n_hex=current_state.modulus_n_hex,
            generator_hex=current_state.generator_hex,
        ),
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
        x_value_hex=x_value_hex,
        x_nonce=x_nonce,
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
