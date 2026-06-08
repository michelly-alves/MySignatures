from __future__ import annotations
from enum import IntEnum
from datetime import datetime
from typing import Optional
import pydantic
from sqlalchemy import Boolean, Column, DateTime, func
from app.db.base import Base
from pydantic import BaseModel, EmailStr
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship

class Role(IntEnum):
    COMPANY = 0
    ADMIN = 1
    SIGNER = 2


class User(Base):
    __tablename__ = "user_account"

    user_id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)
    role = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    signers = relationship("Signer", back_populates="user")
    company = relationship(
        "Company",
        back_populates="user",
        uselist=False
    )
    reset_tokens = relationship("ResetPasswordToken", back_populates="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    otp_verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

class UpdateUser(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[int] = None 
    name: Optional[str] = None 
    contact_email: Optional[EmailStr] = None  
    phone_number: Optional[str] = None  
    legal_name: Optional[str] = None  
