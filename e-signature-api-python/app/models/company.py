from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class Company(Base):
    __tablename__ = "company"

    company_id = Column(Integer, primary_key=True)

    legal_name = Column(String, nullable=False)
    tax_id = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False)
    phone_number = Column(String(20), nullable=True)

    user_id = Column(
        Integer,
        ForeignKey("user_account.user_id"),
        nullable=False,
        unique=True
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship(
        "User",
        back_populates="company",
        uselist=False
    )