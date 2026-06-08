from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

from app.models.user import User


class ResetPasswordToken(Base):
    """Token hexadecimal para redefinição de senha via fluxo 'esqueci minha senha'."""
    __tablename__ = "reset_password_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_account.user_id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship(User, back_populates="reset_tokens")


class NotificationToken(Base):
    """
    Registra o JTI (JWT ID) dos tokens de notificação enviados por e-mail.
    Garante uso único: após consumido pelo endpoint /auth/exchange-token,
    o registro é deletado, impedindo replay do link.
    """
    __tablename__ = "notification_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(36), unique=True, nullable=False)   # UUID4
    user_id = Column(Integer, ForeignKey("user_account.user_id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)