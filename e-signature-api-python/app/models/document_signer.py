from sqlalchemy import Column, Integer, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class DocumentSigner(Base):
    __tablename__ = "document_signer"

    document_id = Column(
        Integer,
        ForeignKey("document.document_id"),
        primary_key=True,
    )

    signer_id = Column(
        Integer,
        ForeignKey("signer.signer_id"),
        primary_key=True,
    )

    status_id = Column(
        Integer,
        ForeignKey("signer_status.status_id"),
        nullable=False,
        default=1,
    )

    face_match_score = Column(Float, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    document = relationship("Document", lazy="joined")
    signer = relationship("Signer", lazy="joined")

    @property
    def signer_name(self) -> str | None:
        return self.signer.full_name if self.signer else None

    @property
    def signer_email(self) -> str | None:
        return self.signer.contact_email if self.signer else None
