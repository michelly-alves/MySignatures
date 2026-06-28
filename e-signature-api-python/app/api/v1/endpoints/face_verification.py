import datetime
import uuid
import logging
from pathlib import Path
import base64

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.signer import Signer
from app.models.document_signer import DocumentSigner
from app.models.signer_status import SignerStatus
from app.models.user import Role, User
from app.models.face_verify import FaceVerifyRequest, LivenessVerifyRequest
from app.dependencies.auth import get_current_user, require_otp_verified
from app.api.v1.responses import err, _401, _500
from app.services.face_recognition import (
    compare_embeddings,
    extract_face_embedding_from_path,
    extract_face_embedding_and_yaw_from_bytes,
    extract_face_pose_from_bytes,
)
from app.utils.timing import log_duration

router = APIRouter(prefix="/face-verification", tags=["Face Verification"])

SIMILARITY_THRESHOLD = 0.40
YAW_FRONT_MAX  = 20.0
YAW_DELTA_MIN  = 8.0   

logger = logging.getLogger(__name__)


def _decode_image(image_base64: str) -> bytes:
    try:
        return base64.b64decode(image_base64)
    except Exception as exc:
        raise HTTPException(400, "Imagem inválida") from exc


def _validate_liveness_poses(
    front_yaw: float,
    left_bytes: bytes,
    right_bytes: bytes,
) -> tuple[bool, dict]:

    try:
        left_yaw  = extract_face_pose_from_bytes(left_bytes)
        right_yaw = extract_face_pose_from_bytes(right_bytes)

    except ValueError as exc:
        return False, {"error": str(exc)}

    # tolerâncias
    YAW_SIDE_DIFF_MIN = 8.0
    MAX_YAW_ALLOWED = 45.0

    # frontal aceitável
    front_straight = abs(front_yaw) <= YAW_FRONT_MAX

    # diferença relativa ao frontal
    left_from_front  = left_yaw  - front_yaw
    right_from_front = right_yaw - front_yaw
    left_delta  = abs(left_from_front)
    right_delta = abs(right_from_front)

    sufficient_movement = (
        left_delta >= YAW_DELTA_MIN
        and right_delta >= YAW_DELTA_MIN
    )

    side_difference = abs(left_yaw - right_yaw)

    frames_distinct = side_difference >= YAW_SIDE_DIFF_MIN

    # evita poses absurdas
    extreme_pose = (
        abs(left_yaw) > MAX_YAW_ALLOWED
        or abs(right_yaw) > MAX_YAW_ALLOWED
    )

    movement_valid = (
        front_straight
        and sufficient_movement
        and frames_distinct
        and not extreme_pose
    )

    return movement_valid, {
        "front_yaw": round(front_yaw, 2),
        "left_yaw": round(left_yaw, 2),
        "right_yaw": round(right_yaw, 2),

        "front_straight": front_straight,

        "left_delta": round(left_delta, 2),
        "right_delta": round(right_delta, 2),

        "side_difference": round(side_difference, 2),

        "frames_distinct": frames_distinct,
        "sufficient_movement": sufficient_movement,
        "extreme_pose": extreme_pose,

        "yaw_front_max": YAW_FRONT_MAX,
        "yaw_delta_min": YAW_DELTA_MIN,
        "yaw_side_diff_min": YAW_SIDE_DIFF_MIN,
        "max_yaw_allowed": MAX_YAW_ALLOWED,
    }


@router.post("/face-verify/{user_id}", responses=(
    err(400, "Imagem inválida", "Imagem inválida ou rosto não detectado.") |
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para verificar este usuário.") |
    err(404, "Não encontrado", "Signatário não encontrado ou biometria não cadastrada.") |
    _500
))
async def verify_face(
    user_id: int,
    payload: FaceVerifyRequest,
    document_id: int | None = None,
    current_user: User = Depends(require_otp_verified),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.ADMIN and current_user.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para verificar este usuário."
        )

    logger.info("Iniciando verificação facial | user_id=%s", user_id)

    try:
        result = await db.execute(
            select(Signer)
            .where(
                Signer.user_id == user_id,
                Signer.deleted_at.is_(None),
            )
            .order_by(Signer.signer_id.desc())
        )
        signer = result.scalars().first()
    except Exception:
        logger.exception("Erro ao buscar signer")
        raise HTTPException(500, "Erro ao buscar signatário")

    if not signer:
        raise HTTPException(404, "Signer não encontrado")

    try:
        stmt = select(DocumentSigner).where(DocumentSigner.signer_id == signer.signer_id)
        if document_id is not None:
            stmt = stmt.where(DocumentSigner.document_id == document_id)
        else:
            stmt = stmt.order_by(DocumentSigner.document_id.desc())
        result = await db.execute(stmt)
        doc_signer = result.scalars().first()
    except Exception:
        logger.exception("Erro ao buscar document_signer")
        raise HTTPException(500, "Erro ao validar vínculo")

    if not doc_signer:
        raise HTTPException(404, "Signer não vinculado a documento")

    reference_embedding = doc_signer.face_embedding or signer.face_embedding
    if not reference_embedding:
        raise HTTPException(404, "Biometria não cadastrada")

    try:
        upload_dir = Path("uploads/selfies")
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4()}.jpg"
        selfie_path = upload_dir / filename

        image_bytes = base64.b64decode(payload.live_image_base64)
        selfie_path.write_bytes(image_bytes)

        logger.info("Selfie salva | path=%s", selfie_path)
    except Exception:
        logger.exception("Erro ao converter imagem base64")
        raise HTTPException(400, "Imagem inválida")

    try:
        with log_duration(logger, "Reconhecimento Facial (extração + comparação)", user_id=user_id):
            selfie_embedding = extract_face_embedding_from_path(
                str(selfie_path)
            )
            similarity = compare_embeddings(
                stored_embedding=reference_embedding,
                selfie_embedding=selfie_embedding,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro ao extrair embedding")
        raise HTTPException(400, "Rosto não detectado")

    verified = similarity >= SIMILARITY_THRESHOLD

    try:
        if verified:
            doc_signer.status_id = SignerStatus.IDENTITY_VERIFIED.value
            doc_signer.verified_at = datetime.datetime.utcnow()
        else:
            doc_signer.status_id = SignerStatus.IDENTITY_FAILED.value

        doc_signer.face_match_score = similarity

        await db.commit()
        await db.refresh(doc_signer)
    except Exception:
        logger.exception("Erro ao salvar resultado")
        raise HTTPException(500, "Erro ao salvar verificação")

    logger.info(
        "Verificação concluída | verified=%s score=%.4f",
        verified,
        similarity,
    )

    return {
        "verified": verified,
        "similarity_score": similarity,
        "threshold": SIMILARITY_THRESHOLD,
    }


@router.post("/documents/{document_id}/liveness-check", responses=(
    err(400, "Dados inválidos", "Frames obrigatórios ausentes ou rosto não detectado no frame frontal.") |
    _401 |
    err(403, "Sem permissão", "Apenas signatários podem validar prova de vida.") |
    err(404, "Não encontrado", "Signatário não encontrado ou não vinculado a este documento.") |
    _500
))
async def verify_document_liveness(
    document_id: int,
    payload: LivenessVerifyRequest,
    current_user: User = Depends(require_otp_verified),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.SIGNER:
        raise HTTPException(403, "Apenas signatários podem validar prova de vida.")

    frames = {frame.step: frame for frame in payload.frames}
    missing = [step for step in ("front", "left", "right") if step not in frames]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Frames obrigatórios ausentes: {', '.join(missing)}",
        )

    result = await db.execute(
        select(Signer)
        .where(
            Signer.user_id == current_user.user_id,
            Signer.deleted_at.is_(None),
        )
        .order_by(Signer.signer_id.desc())
    )
    signer = result.scalars().first()

    if not signer:
        raise HTTPException(404, "Signatário não encontrado")

    if not signer.face_embedding:
        raise HTTPException(404, "Biometria não cadastrada")

    result = await db.execute(
        select(DocumentSigner).where(
            DocumentSigner.document_id == document_id,
            DocumentSigner.signer_id == signer.signer_id,
        )
    )
    doc_signer = result.scalar_one_or_none()
    if not doc_signer:
        raise HTTPException(404, "Signatário não vinculado a este documento")

    reference_embedding = doc_signer.face_embedding or signer.face_embedding
    if not reference_embedding:
        raise HTTPException(404, "Biometria não cadastrada para este documento")

    front_bytes = _decode_image(frames["front"].image_base64)
    left_bytes = _decode_image(frames["left"].image_base64)
    right_bytes = _decode_image(frames["right"].image_base64)

    with log_duration(logger, "Prova de Vida (biometria + pose 3 frames)", document_id=document_id):
        try:
            selfie_embedding, front_yaw = extract_face_embedding_and_yaw_from_bytes(front_bytes)
        except Exception:
            logger.exception("Erro ao extrair embedding frontal")
            raise HTTPException(400, "Rosto não detectado no frame frontal")

        similarity = compare_embeddings(
            stored_embedding=reference_embedding,
            selfie_embedding=selfie_embedding,
        )

        face_valid = similarity >= SIMILARITY_THRESHOLD
        movement_valid, movement_metrics = _validate_liveness_poses(
            front_yaw=front_yaw,
            left_bytes=left_bytes,
            right_bytes=right_bytes,
        )
    verified = face_valid and movement_valid

    if verified:
        doc_signer.status_id = SignerStatus.IDENTITY_VERIFIED.value
        doc_signer.verified_at = datetime.datetime.utcnow()
    else:
        doc_signer.status_id = SignerStatus.IDENTITY_FAILED.value

    doc_signer.face_match_score = similarity

    await db.commit()
    await db.refresh(doc_signer)

    return {
        "verified": verified,
        "face_valid": face_valid,
        "movement_valid": movement_valid,
        "similarity_score": similarity,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "movement_metrics": movement_metrics,
    }
