from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user, require_otp_verified
from app.models.user import Role, User
from app.api.v1.responses import err, _401, _422, _500
from app.schemas.signature import (
    DocumentSignatureSummaryResponse,
    SignDocumentRequest,
    SignDocumentResponse,
    SignatureProofResponse,
)
from app.services import document_service, signature_service

router = APIRouter(prefix="/documents", tags=["Signatures"])


@router.post(
    "/{document_id}/sign",
    response_model=SignDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=(
        err(400, "Dados inválidos", "Documento já assinado ou assinatura inválida.") |
        _401 |
        err(403, "Sem permissão", "Apenas signatários podem assinar documentos.") |
        err(404, "Não encontrado", "Documento não encontrado.") |
        _422 |
        _500
    ),
)
async def sign_document(
    document_id: int,
    payload: SignDocumentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_otp_verified),
):
    if current_user.role != Role.SIGNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas signatários podem assinar documentos."
        )

    try:
        result = await signature_service.sign_document(
            db=db,
            user=current_user,
            document_id=document_id,
            payload=payload,
            ip_address=request.client.host if request.client else None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    signature = result["signature"]
    state = result["state"]
    element = result["element"]
    witness = result["witness"]
    signer = result["signer"]

    return SignDocumentResponse(
        document_id=document_id,
        signer_id=signer.signer_id,
        signature_id=signature.signature_id,
        document_hash=element.hash_hex,
        accumulator_state_id=state.state_id,
        accumulator_value_hex=state.state_value_hex,
        x_value_hex=element.x_value_hex,
        x_nonce=element.x_nonce,
        element_id=element.element_id,
        witness_value_hex=witness.witness_value_hex,
        signed_at=signature.signed_at,
    )


@router.get("/{document_id}/signature-proof", response_model=SignatureProofResponse, responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para acessar a prova deste documento.") |
    err(404, "Não encontrado", "Assinatura/prova não encontrada para este documento.") |
    _500
))
async def get_signature_proof(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = await document_service.can_user_access_document(
        db,
        current_user,
        document_id,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar a prova deste documento."
        )

    result = await signature_service.get_signature_proof(
        db=db,
        user=current_user,
        document_id=document_id,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura/prova não encontrada para este documento."
        )

    signature = result["signature"]
    state = result["state"]
    element = result["element"]
    witness = result["witness"]
    signer = result["signer"]

    return SignatureProofResponse(
        document_id=document_id,
        signature_id=signature.signature_id,
        document_hash=element.hash_hex,
        public_key_pem=result["public_key_pem"],
        accumulator_state_id=state.state_id,
        accumulator_value_hex=state.state_value_hex,
        modulus_n_hex=state.modulus_n_hex,
        generator_hex=state.generator_hex,
        x_value_hex=element.x_value_hex,
        x_nonce=element.x_nonce,
        witness_value_hex=witness.witness_value_hex,
        witness_valid=result["witness_valid"],
        validation_code=signature.validation_code,
        validation_url=signature.validation_url,
        signed_file_path=signature.signed_file_path,
    )


@router.get(
    "/{document_id}/signature-summary",
    response_model=DocumentSignatureSummaryResponse,
    responses=(
        _401 |
        err(403, "Sem permissão", "Você não tem permissão para acessar a assinatura deste documento.") |
        err(404, "Não encontrado", "Documento ainda não possui assinatura.") |
        _500
    ),
)
async def get_document_signature_summary(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = await document_service.can_user_access_document(
        db,
        current_user,
        document_id,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar a assinatura deste documento."
        )

    summary = await signature_service.get_document_signature_summary(
        db=db,
        document_id=document_id,
    )
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento ainda não possui assinatura."
        )

    return DocumentSignatureSummaryResponse(**summary)
