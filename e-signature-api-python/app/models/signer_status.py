from enum import IntEnum
from sqlalchemy import Column, Integer, String
from app.db.base import Base


class SignerStatus(IntEnum):
    PENDING = 1
    IDENTITY_VERIFIED = 2
    IDENTITY_FAILED = 3
    SIGNED = 4


class SignerStatusModel(Base):
    __tablename__ = "signer_status"

    status_id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String(50), nullable=False, unique=True)
