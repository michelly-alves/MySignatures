import secrets
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.db import get_db
from app.schemas.otp import OtpRequest, OtpResponse, VerifyOtpRequest
from app.services.whatsapp import send_otp_via_whatsapp
from app.dependencies.auth import get_current_user
from app.models.signer import Signer
from app.models.company import Company
from app.models.user import Role, User
from app.api.v1.responses import err, _401, _422, _500

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/otp", tags=["otp"])

_MAX_ATTEMPTS = 5 
_OTP_MAX_PER_WINDOW = 3   
_OTP_WINDOW_SECONDS = 10 * 60  
_otp_ip_attempts: dict[str, dict] = {}


def _check_otp_rate_limit(ip: str) -> None:
    now = time.monotonic()
    record = _otp_ip_attempts.get(ip, {"count": 0, "window_start": now})
    if now - record["window_start"] > _OTP_WINDOW_SECONDS:
        record = {"count": 0, "window_start": now}
    if record["count"] >= _OTP_MAX_PER_WINDOW:
        remaining = int(_OTP_WINDOW_SECONDS - (now - record["window_start"]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas solicitações de OTP. Tente novamente em {remaining} segundos.",
        )
    record["count"] += 1
    _otp_ip_attempts[ip] = record


async def _save_and_send_otp(
    db: AsyncSession,
    email: str,
    phone_number: str,
) -> OtpResponse:
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=5)

    query = text("""
        INSERT INTO otp_codes (email, phone_number, code, expires_at, used, attempts)
        VALUES (:email, :phone, :code, :expires_at, FALSE, 0)
        ON CONFLICT (email) DO UPDATE
        SET code       = EXCLUDED.code,
            expires_at = EXCLUDED.expires_at,
            phone_number = EXCLUDED.phone_number,
            used       = FALSE,
            attempts   = 0
    """)

    try:
        await db.execute(query, {
            "email": email,
            "phone": phone_number,
            "code": otp_code,
            "expires_at": expires_at,
        })
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao salvar o código OTP",
        )

    try:
        message_sid = await send_otp_via_whatsapp(phone_number, otp_code)
        logger.info(
            "OTP gerado e enfileirado | email=%s | twilio_sid=%s | "
            "Falhas de entrega assíncronas chegam via POST /webhooks/twilio-status",
            email, message_sid,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )

    return OtpResponse(
        message="Código OTP enviado para o seu WhatsApp.",
        expires_at=expires_at,
    )


@router.post("/generate", response_model=OtpResponse, responses=(
    _422 |
    err(429, "Muitas requisições", "Muitas solicitações de OTP. Tente novamente em N segundos.") |
    _500 |
    err(502, "Serviço indisponível", "Falha ao enviar OTP via WhatsApp. Tente novamente em instantes.")
))
async def generate_otp(
    data: OtpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> OtpResponse:
    ip = request.client.host if request.client else "unknown"
    _check_otp_rate_limit(ip)

    email = str(data.email)

    phone_number: str | None = None

    result = await db.execute(
        select(Signer)
        .join(User, Signer.user_id == User.user_id)
        .where(User.email == email, Signer.deleted_at.is_(None))
        .order_by(Signer.signer_id.desc())
    )
    signer = result.scalars().first()
    if signer:
        phone_number = signer.phone_number
    else:
        result = await db.execute(
            select(Company)
            .join(User, Company.user_id == User.user_id)
            .where(User.email == email, Company.deleted_at.is_(None))
            .order_by(Company.company_id.desc())
        )
        company = result.scalars().first()
        if company:
            phone_number = company.phone_number

    if not phone_number:
        return OtpResponse(
            message="Se o e-mail estiver cadastrado, o código será enviado ao WhatsApp registrado.",
            expires_at=None,
        )

    return await _save_and_send_otp(
        db=db,
        email=email,
        phone_number=phone_number,
    )


@router.post("/generate/current", response_model=OtpResponse, responses=(
    err(400, "OTP já validado", "OTP já validado para este usuário.") |
    _401 |
    err(403, "Sem permissão", "A validação por OTP é exigida apenas para signatários.") |
    err(404, "Não encontrado", "Dados do signatário não encontrados.") |
    _500 |
    err(502, "Serviço indisponível", "Falha ao enviar OTP via WhatsApp. Tente novamente em instantes.")
))
async def generate_current_user_otp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OtpResponse:
    if current_user.role != Role.SIGNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A validação por OTP é exigida apenas para signatários.",
        )

    if current_user.otp_verified_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP já validado para este usuário.",
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dados do signatário não encontrados.",
        )

    return await _save_and_send_otp(
        db=db,
        email=current_user.email,
        phone_number=signer.phone_number,
    )


@router.post("/verify", responses=(
    err(400, "Código inválido", "Código inválido, expirado ou já utilizado.") |
    _422 |
    _500
))
async def verify_otp(
    data: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT code, expires_at, used, attempts
            FROM otp_codes
            WHERE email = :email
        """),
        {"email": data.email},
    )
    record = result.fetchone()

    if not record:
        raise HTTPException(status_code=400, detail="Código inválido")

    code, expires_at, used, attempts = record

    if used:
        raise HTTPException(status_code=400, detail="Código já utilizado")

    if attempts >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=400,
            detail="Número máximo de tentativas atingido. Solicite um novo código.",
        )

    if datetime.now(tz=timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Código expirado")

    await db.execute(
        text("UPDATE otp_codes SET attempts = attempts + 1 WHERE email = :email"),
        {"email": data.email},
    )
    await db.commit()

    if not secrets.compare_digest(code, data.code):
        raise HTTPException(status_code=400, detail="Código inválido")

    now = datetime.now(tz=timezone.utc)

    await db.execute(
        text("UPDATE otp_codes SET used = TRUE WHERE email = :email"),
        {"email": data.email},
    )

    await db.execute(
        text("""
            UPDATE user_account
            SET otp_verified_at = :verified_at,
                updated_at      = :verified_at
            WHERE email      = :email
              AND deleted_at IS NULL
        """),
        {"email": data.email, "verified_at": now},
    )
    await db.commit()

    return {"message": "Validação bem-sucedida!"}
