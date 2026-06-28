from fastapi import status
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import base64
import logging
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization

from app.services.user_service import *
from app.schemas.user import *
from app.db import get_db
from app.dependencies.auth import get_current_user, get_optional_current_user, require_otp_verified
from app.security.roles import require_roles
from app.models.user import Role, User
from app.models.signer import Signer
from app.models.signer_key_history import SignerKeyHistory
from app.models.audit_log import AuditLog
from app.services.face_recognition import (
    compare_embeddings,
    extract_face_embedding_from_bytes,
)
from app.services.signature_service import _same_public_key
from app.utils.timing import log_duration
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.responses import err, _401, _422, _500
from pydantic import BaseModel

FACE_SIMILARITY_THRESHOLD = 0.40

router = APIRouter(prefix="/api")


def _is_admin(user: User) -> bool:
    return user.role == Role.ADMIN


def _is_self_or_admin(current_user: User, user_id: int) -> bool:
    return _is_admin(current_user) or current_user.user_id == user_id


def _get_create_user_permission_error(
    current_user: User | None,
    payload: CreateUser
) -> str | None:
    requested_role = int(payload.role)

    if current_user is None:
        if requested_role != Role.COMPANY:
            return "Cadastro público permite criar apenas usuário empresa."
        return None

    if _is_admin(current_user):
        return None

    if current_user.role == Role.COMPANY:
        if requested_role != Role.SIGNER:
            return "Usuário empresa pode criar apenas usuários signatários."
        return None

    return "Usuário signatário não tem permissão para criar novos usuários."

@router.get("/me", responses=_401 | _500)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_full_user_profile(db, current_user)

@router.post("/users", response_model=UserResponse, status_code=201, responses=(
    err(400, "Dados inválidos", "E-mail já cadastrado ou dados inválidos.") |
    err(403, "Sem permissão", "Usuário signatário não tem permissão para criar novos usuários.") |
    _422 |
    _500
))
async def create_user_endpoint(
    payload: CreateUser,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    permission_error = _get_create_user_permission_error(current_user, payload)
    if permission_error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=permission_error
        )

    try:
        user = await create_user(db, payload)
        return UserResponse.from_orm(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except SQLAlchemyError:
        logging.exception("Erro de banco ao criar usuário")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Erro ao acessar o banco de dados"
        )

    except Exception:
        logging.exception("Erro interno ao criar usuário")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor"
        )
        
@router.get("/users", response_model=list[UserResponse], responses=(
    _401 |
    err(403, "Sem permissão", "Apenas administradores podem listar todos os usuários.") |
    _500
))
async def list_users(
    current_user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    return await get_all_users(db)

@router.get("/users/{user_id}", responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para acessar este usuário.") |
    err(404, "Não encontrado", "Usuário não encontrado.") |
    _500
))
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not _is_self_or_admin(current_user, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este usuário."
        )

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return await get_full_user_profile(db, user)

@router.put("/users/{user_id}", response_model=UserResponse, responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para alterar este usuário.") |
    err(404, "Não encontrado", "Usuário não encontrado.") |
    _422 |
    _500
))
async def update_user_endpoint(
    user_id: int,
    payload: UpdateUser,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not _is_self_or_admin(current_user, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para alterar este usuário."
        )

    if not _is_admin(current_user) and payload.role is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para alterar o tipo do usuário."
        )

    user = await update_user(db, user_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user

@router.delete("/users/{user_id}", responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para remover este usuário.") |
    err(404, "Não encontrado", "Usuário não encontrado.") |
    _500
))
async def delete_user_endpoint(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not _is_self_or_admin(current_user, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para remover este usuário."
        )

    success = await delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return {"message": "Usuário removido com sucesso"}


class _RegisterKeyRequest(BaseModel):
    public_key_pem: str


@router.put(
    "/signer/public-key",
    responses=(
        _401 |
        err(400, "Já registrada", "Chave de assinatura já registrada para este signatário.") |
        err(403, "Sem permissão", "Apenas signatários podem registrar chave de assinatura.") |
        err(404, "Não encontrado", "Signatário não encontrado.") |
        _500
    ),
)
async def register_signing_key(
    payload: _RegisterKeyRequest,
    current_user: User = Depends(require_otp_verified),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.SIGNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas signatários podem registrar chave de assinatura.")

    result = await db.execute(
        select(Signer)
        .where(Signer.user_id == current_user.user_id, Signer.deleted_at.is_(None))
        .order_by(Signer.signer_id.desc())
    )
    signer = result.scalars().first()

    if not signer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signatário não encontrado.")

    if signer.public_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Chave de assinatura já registrada. Para redefinir, entre em contato com o suporte.",
        )

    signer.public_key = payload.public_key_pem
    await db.commit()
    return {"message": "Chave de assinatura registrada com sucesso."}


class _RotateKeyRequest(BaseModel):
    new_public_key_pem: str
    live_image_base64: str


@router.post(
    "/signer/rotate-key",
    responses=(
        _401 |
        err(400, "Dados inválidos", "Nova chave pública inválida ou igual à atual.") |
        err(403, "Falha na verificação", "Verificação facial não confirmou a identidade.") |
        err(404, "Não encontrado", "Signatário ou chave atual não encontrados.") |
        _500
    ),
)
async def rotate_signing_key(
    payload: _RotateKeyRequest,
    request: Request,
    current_user: User = Depends(require_otp_verified),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotaciona a chave de assinatura do signatário (perda do .ekey ou da senha).

    Exige re-autenticação forte: OTP verificado (via require_otp_verified) +
    verificação facial em tempo real contra a biometria cadastrada. A chave
    antiga é revogada e movida para signer_key_history; assinaturas anteriores
    permanecem válidas, pois cada uma guarda a chave usada no momento.

    NÃO há recuperação da chave perdida (posse exclusiva): gera-se uma nova.
    """
    if current_user.role != Role.SIGNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Apenas signatários podem rotacionar a chave de assinatura.",
        )

    result = await db.execute(
        select(Signer)
        .where(Signer.user_id == current_user.user_id, Signer.deleted_at.is_(None))
        .order_by(Signer.signer_id.desc())
    )
    signer = result.scalars().first()
    if not signer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signatário não encontrado.")
    if not signer.public_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Não há chave registrada para rotacionar. Registre a chave primeiro.",
        )
    if not signer.face_embedding:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Biometria não cadastrada; rotação não pode ser autenticada.",
        )

    # Valida a nova chave pública e garante que é realmente diferente da atual.
    try:
        serialization.load_pem_public_key(payload.new_public_key_pem.encode("utf-8"))
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nova chave pública inválida.")
    if _same_public_key(payload.new_public_key_pem, signer.public_key):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A nova chave é igual à atual; gere um novo par de chaves.",
        )

    # Re-verificação facial contra a biometria cadastrada.
    try:
        image_bytes = base64.b64decode(payload.live_image_base64)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Imagem inválida.")
    try:
        with log_duration(logger, "Rotação de Chave (verificação facial)", user_id=current_user.user_id):
            live_embedding = extract_face_embedding_from_bytes(image_bytes)
            similarity = compare_embeddings(
                stored_embedding=signer.face_embedding,
                selfie_embedding=live_embedding,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro na verificação facial durante rotação de chave")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rosto não detectado na imagem enviada.")

    if similarity < FACE_SIMILARITY_THRESHOLD:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Verificação facial não confirmou a identidade. Rotação cancelada.",
        )

    # Revoga a chave antiga (histórico) e ativa a nova.
    old_public_key = signer.public_key
    db.add(SignerKeyHistory(
        signer_id=signer.signer_id,
        public_key=old_public_key,
        reason="Rotação por perda de chave/senha (re-verificação facial + OTP)",
        revoked_by=current_user.user_id,
    ))
    signer.public_key = payload.new_public_key_pem
    signer.updated_at = datetime.now(tz=timezone.utc)

    db.add(AuditLog(
        user_id=current_user.user_id,
        entity_name="signer",
        entity_id=signer.signer_id,
        action="SIGNER_KEY_ROTATED",
        description=(
            f"Chave de assinatura rotacionada. signer_id={signer.signer_id}; "
            f"similaridade_facial={similarity:.4f}"
        ),
        ip_address=request.client.host if request.client else None,
    ))

    await db.commit()
    logger.info(
        "Chave de assinatura rotacionada | signer_id=%s | user_id=%s",
        signer.signer_id,
        current_user.user_id,
    )
    return {"message": "Chave de assinatura rotacionada com sucesso."}
