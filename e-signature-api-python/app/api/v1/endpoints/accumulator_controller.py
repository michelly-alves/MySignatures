from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.accumulator_service import (
    get_latest_state,
    get_public_registry_page,
    state_fingerprint,
)
from app.api.v1.responses import err, _500

router = APIRouter(prefix="/accumulator", tags=["Accumulator"])


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
