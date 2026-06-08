from fastapi import Depends, HTTPException, status
from app.models.user import Role, User
from app.dependencies.auth import get_current_user


def require_roles(*allowed_roles: Role):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return dependency
