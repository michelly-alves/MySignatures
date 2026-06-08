from pydantic import BaseModel, EmailStr
from datetime import datetime


class OtpRequest(BaseModel):
    email: EmailStr
    phone_number: str


class OtpResponse(BaseModel):
    message: str
    expires_at: datetime | None = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str
