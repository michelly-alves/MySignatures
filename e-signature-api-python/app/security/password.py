import re

import bcrypt

_PASSWORD_RULES = (
    (lambda p: len(p) >= 8, "A senha deve ter pelo menos 8 caracteres"),
    (lambda p: re.search(r"[A-Z]", p), "A senha deve conter pelo menos uma letra maiúscula"),
    (lambda p: re.search(r"\d", p), "A senha deve conter pelo menos um número"),
    (lambda p: re.search(r"[^A-Za-z0-9]", p), "A senha deve conter pelo menos um caractere especial"),
)


def validate_password_strength(password: str) -> str:
    """Valida a força da senha e a retorna intacta; levanta ValueError na 1ª regra falha."""
    if not password or not password.strip():
        raise ValueError("A senha é obrigatória")
    for check, message in _PASSWORD_RULES:
        if not check(password):
            raise ValueError(message)
    return password


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )
