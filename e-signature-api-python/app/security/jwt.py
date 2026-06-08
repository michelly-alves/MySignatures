from datetime import datetime, timedelta, timezone
from typing import Dict

from jose import jwt, JWTError
from pydantic import BaseModel

from app.core.config import settings


ALGORITHM = "HS256"
_NOTIFICATION_PURPOSE = "notification"


class Claims(BaseModel):
    sub: str
    exp: int
    iat: int


class NotificationClaims(BaseModel):
    sub: str      
    jti: str      
    purpose: str  
    exp: int
    iat: int

def create_jwt(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, int | str] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET must be set")
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def validate_jwt(token: str) -> Claims:
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET must be set")
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={
                "require_exp": True,
                "require_iat": True,
                "require_sub": True,
            },
        )
    except JWTError:
        raise ValueError("Invalid or expired token")
    return Claims(**decoded)


def create_notification_jwt(user_id: str, jti: str) -> str:
    """
    Gera um JWT assinado para links de notificação enviados por e-mail.

    - Validade: 48 horas.
    - Claim `jti`: UUID4 armazenado na tabela `notification_tokens`; garante
      que o link só possa ser consumido uma única vez (anti-replay).
    - Claim `purpose`: constante "notification"; impede que este token
      seja aceito como JWT de sessão pelos endpoints protegidos.
    """
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, int | str] = {
        "sub": user_id,
        "jti": jti,
        "purpose": _NOTIFICATION_PURPOSE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=48)).timestamp()),
    }
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET must be set")
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def validate_notification_jwt(token: str) -> NotificationClaims:
    """
    Valida a assinatura e a validade do JWT de notificação.
    Não verifica o JTI no banco — essa responsabilidade é do endpoint consumidor.
    Lança ValueError se o token for inválido, expirado ou não for de notificação.
    """
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET must be set")
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
    except JWTError:
        raise ValueError("Token de notificação inválido ou expirado")

    claims = NotificationClaims(**decoded)
    if claims.purpose != _NOTIFICATION_PURPOSE:
        raise ValueError("Token não é de notificação")
    return claims
