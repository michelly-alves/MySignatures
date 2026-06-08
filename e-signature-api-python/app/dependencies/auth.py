from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.user import Role, User
from app.security.jwt import validate_jwt

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        token = credentials.credentials
        claims = validate_jwt(token)
        user_id = int(claims.sub)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        claims = validate_jwt(token)
        user_id = int(claims.sub)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def require_otp_verified(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Garante que signatários tenham concluído a verificação OTP de primeiro acesso.

    - SIGNER sem otp_verified_at → 403 com instrução clara.
    - COMPANY e ADMIN → passam sem restrição (não precisam de OTP).

    Use este Depends nos endpoints que signatários acessam após o
    onboarding (assinar, verificação facial, listagem de documentos pendentes).
    Não use em /api/me nem nos endpoints de geração/verificação de OTP,
    pois eles fazem parte do próprio fluxo de ativação.
    """
    if (
        current_user.role == Role.SIGNER
        and current_user.otp_verified_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Verificação de identidade pendente. "
                "Confirme o código OTP enviado ao seu WhatsApp para continuar."
            ),
        )
    return current_user
