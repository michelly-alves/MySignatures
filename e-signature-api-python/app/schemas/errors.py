from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str

    model_config = {"json_schema_extra": {"example": {"detail": "Descrição do erro"}}}
