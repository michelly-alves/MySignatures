from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from app.db.base import Base


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, nullable=False, unique=True)
    phone_number = Column(String(20), nullable=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, server_default="false")
    # Contador de tentativas incorretas; ao atingir o limite o código é invalidado.
    attempts = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
