from sqlalchemy import Column, DateTime, Integer, String, Text, func
from app.db.base import Base


class DigitalSignature(Base):
    __tablename__ = "digital_signature"

    signature_id = Column(Integer, primary_key=True)
    doc_sign_id = Column(Integer, nullable=False)
    signer_id = Column(Integer, nullable=False)
    signature_data = Column(Text, nullable=False)
    public_key_pem = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    validation_code = Column(String(64), nullable=True)
    validation_url = Column(Text, nullable=True)
    signed_file_path = Column(Text, nullable=True)
    signed_file_sha256 = Column(String(64), nullable=True)
    signed_at = Column(DateTime(timezone=True), server_default=func.now())
