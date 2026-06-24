import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.accumulator import AccumulatorElement
from app.models.digital_signature import DigitalSignature
from app.models.user import Role, User
from app.security.roles import require_roles
from app.services.accumulator_service import (
    get_latest_state,
    get_public_registry_page,
    get_single_witness_on_demand,
    state_fingerprint,
)
from app.api.v1.responses import err, _401, _500

router = APIRouter(prefix="/accumulator", tags=["Accumulator"])

# Rate-limit do caminho pericial (testemunha sob demanda): no máximo 60
# solicitações por minuto por administrador, protegendo a operação cara
# (exponenciação modular + escrita) contra abuso/DoS.
_WITNESS_MAX_PER_WINDOW = 60
_WITNESS_WINDOW_SECONDS = 60
_witness_request_counters: dict[str, dict] = {}


def _check_witness_rate_limit(identifier: str) -> None:
    now = time.monotonic()
    record = _witness_request_counters.get(
        identifier, {"count": 0, "window_start": now}
    )
    if now - record["window_start"] > _WITNESS_WINDOW_SECONDS:
        record = {"count": 0, "window_start": now}
    if record["count"] >= _WITNESS_MAX_PER_WINDOW:
        remaining = int(_WITNESS_WINDOW_SECONDS - (now - record["window_start"]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Limite de {_WITNESS_MAX_PER_WINDOW} solicitações de testemunha "
                f"por minuto excedido. Tente novamente em {remaining} segundos."
            ),
        )
    record["count"] += 1
    _witness_request_counters[identifier] = record


@router.get("/current", responses=(
    err(404, "Não inicializado", "Acumulador ainda não inicializado.") |
    _500
))
async def get_current_accumulator_state(
    db: AsyncSession = Depends(get_db),
):
    state = await get_latest_state(db)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Acumulador ainda não inicializado."
        )

    return {
        "state_id": state.state_id,
        "previous_state_id": state.previous_state_id,
        "state_value_hex": state.state_value_hex,
        "generator_hex": state.generator_hex,
        "modulus_n_hex": state.modulus_n_hex,
        "created_at": state.created_at,
        "comments": state.comments,
    }


@router.get("/registry", responses=_500)
async def get_public_accumulator_registry(
    after_state_id: int = Query(
        0,
        ge=0,
        description=(
            "Retorna apenas estados com state_id maior que este valor. "
            "Espelhos devem repetir a chamada com o último state_id recebido "
            "até obterem uma página vazia (sincronização incremental)."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Registro público e auditável da cadeia de estados do acumulador.

    Pensado para ser espelhado/arquivado periodicamente por verificadores
    externos (modelo de transparency log com testemunhas independentes):
    cada item expõe o elo da cadeia, e qualquer um pode verificar toda a
    história com `pow(estado_anterior, x, N) == estado` — uma exponenciação
    por elo, sem confiar neste servidor. O `state_sha256` é a impressão
    digital impressa no selo dos PDFs assinados, permitindo conferir um
    documento em mãos contra o registro espelhado.
    """
    rows = await get_public_registry_page(db, after_state_id=after_state_id, limit=limit)

    items = [
        {
            "state_id": state.state_id,
            "previous_state_id": state.previous_state_id,
            "state_value_hex": state.state_value_hex,
            "state_sha256": state_fingerprint(state.state_value_hex),
            "x_hex": x_value_hex,
            "published_at": published_at,
            "created_at": state.created_at,
        }
        for state, published_at, x_value_hex in rows
    ]

    first_state = rows[0][0] if rows else None
    return {
        "descricao": (
            "Cadeia de estados do acumulador RSA. Para auditar, verifique "
            "cada elo: pow(int(state_value_hex do estado anterior, 16), "
            "int(x_hex, 16), int(modulus_n_hex, 16)) == int(state_value_hex, 16). "
            "x_hex é nulo apenas no estado inicial. Arquive as páginas "
            "periodicamente: cópias independentes deste registro tornam "
            "qualquer reescrita retroativa da cadeia detectável."
        ),
        "modulus_n_hex": first_state.modulus_n_hex if first_state else None,
        "generator_hex": first_state.generator_hex if first_state else None,
        "items": items,
        "next_after_state_id": items[-1]["state_id"] if len(items) == limit else None,
    }


@router.get("/witness/{validation_code}", responses=(
    _401 |
    err(403, "Sem permissão", "Apenas administradores podem gerar testemunhas sob demanda.") |
    err(404, "Não encontrado",
        "Assinatura não encontrada, ou estado anterior à incorporação dela.") |
    err(429, "Limite excedido", "Limite de 60 solicitações por minuto excedido.") |
    _500
))
async def get_witness_for_validation_code(
    validation_code: str,
    state_id: int | None = Query(
        None,
        ge=1,
        description=(
            "Estado-alvo da prova (ex.: um estado arquivado por um espelho "
            "do registro público). Se omitido, usa o estado mais recente."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(Role.COMPANY)),
):
    """
    Testemunha sob demanda (caminho pericial do modo lazy) — ENDURECIDO.

    Acesso restrito a administradores e limitado a 60 solicitações por minuto,
    por se tratar de operação criptográfica cara com escrita no banco.

    Gera a testemunha de pertencimento de UMA assinatura (identificada pelo
    código de validação) contra o estado solicitado, calculada isoladamente
    (``w = g^(produto dos demais x) mod N``): uma exponenciação modular e UMA
    linha inserida — sem o lote RootFactor, evitando a amplificação O(n²) de
    armazenamento. Memoizado por (elemento, estado). Verificação pelo perito:
    pow(int(witness_hex,16), int(x_hex,16), int(modulus_n_hex,16)) ==
    int(state_value_hex,16).
    """
    _check_witness_rate_limit(str(current_user.user_id))

    result = await db.execute(
        select(AccumulatorElement.element_id)
        .join(
            DigitalSignature,
            DigitalSignature.signature_id == AccumulatorElement.signature_id,
        )
        .where(DigitalSignature.validation_code == validation_code)
    )
    element_id = result.scalars().first()
    if element_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada.",
        )

    proof = await get_single_witness_on_demand(db, element_id=element_id, state_id=state_id)
    if proof is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Estado inexistente ou anterior à incorporação desta assinatura "
                "no acumulador."
            ),
        )

    await db.commit()

    return {
        "descricao": (
            "Prova de pertencimento gerada sob demanda contra o estado "
            "solicitado. Verifique: witness^x ≡ estado (mod n). Confira o "
            "state_sha256 com o impresso no selo do PDF ou com um espelho "
            "do registro público (/accumulator/registry)."
        ),
        "validation_code": validation_code,
        **proof,
    }
