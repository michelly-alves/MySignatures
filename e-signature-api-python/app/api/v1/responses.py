from app.schemas.errors import ErrorResponse


def err(code: int, description: str, detail: str) -> dict:
    """Response dict com descrição e exemplo de detail para o Swagger."""
    return {
        code: {
            "model": ErrorResponse,
            "description": description,
            "content": {
                "application/json": {
                    "example": {"detail": detail}
                }
            },
        }
    }

_401 = err(401, "Não autenticado", "Credenciais ausentes ou token inválido/expirado.")
_422 = {422: {"model": ErrorResponse, "description": "Erro de validação dos campos enviados"}}
_500 = err(500, "Erro interno do servidor", "Erro interno do servidor.")

AUTH      = _401 | _422 | _500
AUTH_CRUD = _401 | _422 | _500
AUTH_FULL = _401 | _422 | _500
