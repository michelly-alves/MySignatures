from sqlalchemy import Column, DateTime, Integer, String, Text, func
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    entity_name = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
