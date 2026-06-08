from sqlalchemy import BigInteger, CHAR, Column, DateTime, Integer, String, func
from app.db.base import Base


class IdentityDocument(Base):
    __tablename__ = "identity_document"

    identity_id = Column(BigInteger, primary_key=True, autoincrement=True)
    signer_id = Column(BigInteger, nullable=False)
    document_type = Column(Integer, nullable=False)
    document_number = Column(String(50), nullable=True)
    file_path = Column(String(500), nullable=True)
    mime_type = Column(String(50), nullable=True)
    file_hash = Column(CHAR(64), nullable=False)
    validation_status = Column(Integer, nullable=True, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
