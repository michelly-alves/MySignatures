from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db import get_db
from app.dependencies.auth import get_current_user, require_otp_verified
from app.models.user import User
from app.schemas.document_signer import DocumentSignerResponse
from app.services.document_signer_service import DocumentSignerService
from app.api.v1.responses import err, _401, _500

router = APIRouter(prefix="/document-signers", tags=["Document Signers"])


@router.get(
    "",
    response_model=List[DocumentSignerResponse],
    summary="Listar signatários de documentos",
    responses=(
        _401 |
        err(403, "Sem permissão", "Usuário sem permissão para listar signatários deste documento.") |
        _500
    ),
)
async def list_document_signers(
    document_id: Optional[int] = Query(
        default=None,
        description="Filtrar por documento específico"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_otp_verified),
):
    """
    Retorna vínculos documento/signatário visíveis para o usuário autenticado.

    - ADMIN vê todos.
    - COMPANY vê vínculos dos documentos da própria empresa.
    - SIGNER vê apenas seus próprios vínculos (requer OTP verificado).
    - Se `document_id` for informado, restringe a esse documento.
    """

    return await DocumentSignerService.get_document_signers_for_user(
        db=db,
        user=current_user,
        document_id=document_id,
    )
