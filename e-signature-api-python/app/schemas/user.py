from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime
from enum import IntEnum
from app.models.user import Role
from pydantic import field_validator, model_validator
from app.security.password import validate_password_strength
import re

class Role(IntEnum):
    COMPANY = 0
    ADMIN = 1
    SIGNER = 2


class CreateUser(BaseModel):
    email: EmailStr
    password: str
    role: Role

    # COMPANY
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None

    # SIGNER
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    national_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str):
        return validate_password_strength(value)

    @field_validator(
        "legal_name",
        "tax_id",
        "full_name",
        "phone_number",
        "national_id",
        mode="before"
    )
    @classmethod
    def strip_blank_strings(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_by_role(self):
        if self.role == Role.COMPANY:
            missing = [
                field for field in ["legal_name", "tax_id", "phone_number"]
                if not getattr(self, field)
            ]
            if missing:
                raise ValueError(
                    f"Campos obrigatórios para empresa: {', '.join(missing)}"
                )
            tax_digits = re.sub(r"\D", "", self.tax_id)
            if len(tax_digits) != 14:
                raise ValueError("CNPJ inválido: informe 14 dígitos")

        if self.role == Role.SIGNER:
            missing = [
                f for f in
                ["full_name", "phone_number", "national_id"]
                if not getattr(self, f)
            ]
            if missing:
                raise ValueError(
                    f"Campos obrigatórios para signatário: {', '.join(missing)}"
                )
            national_id_digits = re.sub(r"\D", "", self.national_id)
            if len(national_id_digits) != 11:
                raise ValueError("CPF inválido: informe 11 dígitos")

        return self

class UpdateUser(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[Role] = None

    # COMPANY
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None

    # SIGNER
    name: Optional[str] = None
    full_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    national_id: Optional[str] = None


class UserResponse(BaseModel):
    user_id: int
    email: str
    role: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
