from typing import Optional
from pydantic import BaseModel, EmailStr

class CreateDocument(BaseModel):
    company_id: int
    status_id: int = 1

    signer_full_name: Optional[str]
    signer_phone_number: Optional[str]
    signer_email: Optional[EmailStr]
    signer_national_id: Optional[str]

    file_name: Optional[str]
    file_path: Optional[str]
    hash_sha256: Optional[str]
    photo_id_url: Optional[str]

class UpdateDocument(BaseModel):
    status_id: Optional[int]
