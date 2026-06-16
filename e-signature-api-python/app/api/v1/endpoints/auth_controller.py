import secrets
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, EmailStr, field_validator

from app.core.config import settings
from app.db import get_db
from app.models.user import User
from app.models.auth_models import ResetPasswordToken, NotificationToken
from app.schemas.auth import LoginRequest, TokenResponse
from app.security.jwt import create_jwt, validate_notification_jwt
from app.security.password import verify_password, hash_password, validate_password_strength
from app.dependencies.auth import get_current_user
from app.utils.email import send_forgot_password_email
from app.api.v1.responses import err, _401, _422, _500

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_LOGIN_ATTEMPTS = 5        
_WINDOW_SECONDS = 5 * 60    
_LOCKOUT_SECONDS = 15 * 60  

_login_attempts: dict[str, dict] = {}


def _check_rate_limit(email: str) -> None:
    """Levanta HTTP 429 se a conta estiver bloqueada."""
    now = time.monotonic()
    record = _login_attempts.get(email)
    if record and record["locked_until"] > now:
        remaining = int(record["locked_until"] - now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Conta temporariamente bloqueada por excesso de tentativas. "
                f"Tente novamente em {remaining} segundos."
            ),
        )


def _register_failed_attempt(email: str) -> None:
    """Incrementa o contador; bloqueia a conta ao atingir o limite.

    O lockout NÃO é resetado pelo vencimento da janela — apenas pelo
    login bem-sucedido. Isso fecha o bypass de fazer N-1 tentativas,
    esperar a janela expirar e repetir indefinidamente.
    """
    now = time.monotonic()
    record = _login_attempts.get(email, {
        "count": 0,
        "window_start": now,
        "locked_until": 0.0,
    })

    in_lockout = record["locked_until"] > now
    if not in_lockout and now - record["window_start"] > _WINDOW_SECONDS:
        record = {
            "count": 0,
            "window_start": now,
            "locked_until": record["locked_until"],  # preserva lockout pendente
        }

    record["count"] += 1
    if record["count"] >= _MAX_LOGIN_ATTEMPTS:
        record["locked_until"] = now + _LOCKOUT_SECONDS
        logger.warning(
            "Login bloqueado por excesso de tentativas | email=%s | lockout=%ds",
            email, _LOCKOUT_SECONDS,
        )

    _login_attempts[email] = record


def _clear_attempts(email: str) -> None:
    """Remove o registro após login bem-sucedido."""
    _login_attempts.pop(email, None)


@router.post("/login", response_model=TokenResponse, responses=(
    err(401, "Credenciais inválidas", "Credenciais inválidas.") |
    _422 |
    err(429, "Conta bloqueada", "Conta temporariamente bloqueada por excesso de tentativas. Tente novamente em N segundos.") |
    _500
))
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email)

    _check_rate_limit(email)

    result = await db.execute(
        select(User).where(
            User.email == email,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user or user.password_hash is None or not verify_password(data.password, user.password_hash):
        _register_failed_attempt(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )

    _clear_attempts(email)
    token = create_jwt(str(user.user_id))
    return TokenResponse(access_token=token)

class ExchangeTokenRequest(BaseModel):
    token: str


@router.post("/exchange-token", response_model=TokenResponse, responses=(
    err(400, "Token inválido", "Token inválido, expirado ou já utilizado.") |
    err(404, "Usuário não encontrado", "Usuário não encontrado.") |
    _422 |
    _500
))
async def exchange_notification_token(
    data: ExchangeTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Troca um JWT de notificação (enviado por e-mail) por um JWT de sessão válido.

    O processo garante anti-replay:
    1. Valida a assinatura e a validade do JWT de notificação.
    2. Verifica se o JTI ainda existe em `notification_tokens` (não consumido).
    3. Deleta o registro do JTI (uso único).
    4. Retorna um JWT de sessão para o signatário.
    """
    try:
        claims = validate_notification_jwt(data.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    now = datetime.now(tz=timezone.utc)

    result = await db.execute(
        select(NotificationToken).where(
            NotificationToken.jti == claims.jti,
            NotificationToken.expires_at > now,
        )
    )
    notification_token = result.scalar_one_or_none()

    if not notification_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido, expirado ou já utilizado.",
        )

    await db.delete(notification_token)
    await db.commit()

    user = await db.get(User, notification_token.user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    session_jwt = create_jwt(str(user.user_id))
    return TokenResponse(access_token=session_jwt)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


def _send_reset_email_bg(email: str, reset_link: str) -> None:
    try:
        send_forgot_password_email(email, reset_link)
    except Exception:
        logger.exception("Falha ao enviar e-mail de redefinição para %s", email)


@router.post("/forgot-password", status_code=200, responses=_422 | _500)
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Solicita redefinição de senha.
    Sempre retorna 200 para não revelar se o e-mail está cadastrado.
    """
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user:
        await db.execute(
            delete(ResetPasswordToken).where(
                ResetPasswordToken.user_id == user.user_id
            )
        )

        token_value = secrets.token_hex(32)
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)

        db.add(ResetPasswordToken(
            user_id=user.user_id,
            token=token_value,
            expires_at=expires_at,
        ))
        await db.commit()

        reset_link = (
            f"{settings.FRONTEND_BASE_URL}/set-password?token={token_value}"
        )
        background_tasks.add_task(_send_reset_email_bg, user.email, reset_link)

    return {"message": "Se o e-mail estiver cadastrado, você receberá as instruções em breve."}


class SetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str):
        return validate_password_strength(value)


@router.post("/set-password", responses=(
    err(400, "Token inválido", "Token de ativação inválido, expirado ou já utilizado.") |
    err(404, "Usuário não encontrado", "Usuário não encontrado.") |
    _422 |
    _500
))
async def set_password(
    data: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Define a senha de um usuário.

    Aceita dois formatos de token:
    - **JWT de notificação** (signatários novos convocados via documento):
      validado por assinatura criptográfica + JTI em `notification_tokens`.
    - **Token hexadecimal** (fluxo "esqueci minha senha"):
      validado via lookup em `reset_password_tokens`.
    """
    now_utc = datetime.now(tz=timezone.utc)
    user_id: int | None = None

    is_notification_jwt = data.token.startswith("eyJ")  # header JWT em base64url
    if is_notification_jwt:
        try:
            claims = validate_notification_jwt(data.token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = await db.execute(
            select(NotificationToken).where(
                NotificationToken.jti == claims.jti,
                NotificationToken.expires_at > now_utc,
            )
        )
        notification_token = result.scalar_one_or_none()
        if not notification_token:
            raise HTTPException(
                status_code=400,
                detail="Token de ativação inválido, expirado ou já utilizado.",
            )

        user_id = notification_token.user_id
        await db.delete(notification_token)

    else:
        result = await db.execute(
            select(ResetPasswordToken)
            .where(ResetPasswordToken.token == data.token)
            .where(ResetPasswordToken.expires_at > datetime.now(tz=timezone.utc))
        )
        token_obj = result.scalar_one_or_none()
        if not token_obj:
            raise HTTPException(
                status_code=400,
                detail="Token inválido ou expirado",
            )

        user_id = token_obj.user_id
        await db.delete(token_obj)

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.password_hash = hash_password(data.new_password)
    user.is_active = True
    user.updated_at = datetime.now(tz=timezone.utc)

    await db.commit()
    await db.refresh(user)

    return {"message": "Senha definida com sucesso"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str):
        return validate_password_strength(value)


@router.post("/change-password", responses=(
    err(400, "Senha atual incorreta", "A senha atual está incorreta.") |
    _401 |
    _422 |
    _500
))
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Altera a senha do usuário autenticado.

    Exige a senha atual (reautenticação) e aplica a política de força à nova
    senha. A nova senha não pode ser igual à atual.
    """
    if current_user.password_hash is None or not verify_password(
        data.current_password, current_user.password_hash
    ):
        raise HTTPException(status_code=400, detail="A senha atual está incorreta.")

    if verify_password(data.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="A nova senha deve ser diferente da senha atual.",
        )

    current_user.password_hash = hash_password(data.new_password)
    current_user.updated_at = datetime.now(tz=timezone.utc)

    await db.commit()

    return {"message": "Senha alterada com sucesso"}
