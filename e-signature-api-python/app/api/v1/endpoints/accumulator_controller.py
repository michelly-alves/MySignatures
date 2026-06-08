from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.accumulator_service import get_latest_state
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
