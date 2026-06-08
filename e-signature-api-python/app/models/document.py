from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.db.base import Base

class Document(Base):
    __tablename__ = "document"

    document_id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)

    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    hash_sha256 = Column(String, nullable=False)

    status_id = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    signers = relationship(
        "Signer",
        secondary="document_signer",
        back_populates="documents"
    )

