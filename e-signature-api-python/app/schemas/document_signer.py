from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentSignerResponse(BaseModel):
    document_id: int
    signer_id: int
    status_id: int
    face_match_score: Optional[float]
    verified_at: Optional[datetime]

    class Config:
        from_attributes = True
