from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base
from sqlalchemy.dialects.postgresql import JSONB

class Signer(Base):
    __tablename__ = "signer"

    signer_id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    national_id = Column(String, nullable=False, index=True)
    phone_number = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)

    public_key = Column(String, nullable=True)
    photo_id_url = Column(String, nullable=True)
    face_embedding = Column(JSONB, nullable=True)
    user_id = Column(Integer, ForeignKey("user_account.user_id"), nullable=True)

    user = relationship(
        "User",
        back_populates="signers"
    ) 

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    documents = relationship(
        "Document",
        secondary="document_signer",
        back_populates="signers"
    )

