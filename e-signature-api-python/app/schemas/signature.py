from datetime import datetime
from pydantic import BaseModel, Field


class SignDocumentRequest(BaseModel):
    signature_base64: str = Field(..., min_length=1)
    public_key_pem: str | None = None


class SignDocumentResponse(BaseModel):
    document_id: int
    signer_id: int
    signature_id: int
    document_hash: str
    accumulator_state_id: int
    accumulator_value_hex: str
    x_value_hex: str
    x_nonce: int
    element_id: int
    witness_value_hex: str
    signed_at: datetime | None


class SignatureProofResponse(BaseModel):
    document_id: int
    signature_id: int
    document_hash: str
    public_key_pem: str | None
    accumulator_state_id: int
    accumulator_value_hex: str
    modulus_n_hex: str
    generator_hex: str
    x_value_hex: str
    x_nonce: int
    witness_value_hex: str
    witness_valid: bool
    validation_code: str | None = None
    validation_url: str | None = None
    signed_file_path: str | None = None


class DocumentSignatureSummaryResponse(BaseModel):
    document_id: int
    signature_id: int
    signer_id: int
    signer_name: str
    signed_at: datetime | None
    validation_code: str | None = None
    validation_url: str | None = None
