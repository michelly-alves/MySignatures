from typing import List, Optional
from pydantic import BaseModel, EmailStr


class SignerInput(BaseModel):
    full_name: str
    phone_number: str
    email: EmailStr
    national_id: str
    photo_id_url: Optional[str] = None


class CreateDocument(BaseModel):
    company_id: int
    status_id: int = 1

    file_name: Optional[str] = None
    file_path: Optional[str] = None
    hash_sha256: Optional[str] = None

    signers: List[SignerInput] = []


class UpdateDocument(BaseModel):
    status_id: Optional[int] = None
