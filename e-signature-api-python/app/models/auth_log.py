from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, func
from app.db.base import Base


class AuthLog(Base):
    __tablename__ = "auth_log"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    mfa_type = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    attempts = Column(Integer, nullable=True, server_default="1")
    ip_address = Column(String(45), nullable=True)
    logged_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
