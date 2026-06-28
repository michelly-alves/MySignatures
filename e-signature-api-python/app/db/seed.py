
import os

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.security.password import hash_password, validate_password_strength

DOCUMENT_STATUS = [
    (1, "Criado"),
    (2, "Em andamento"),
    (3, "Assinado"),
    (4, "Cancelado"),
]

SIGNER_STATUS = [
    (1, "PENDING"),
    (2, "IDENTITY_VERIFIED"),
    (3, "IDENTITY_FAILED"),
    (4, "SIGNED"),
]

ROLE_ADMIN = 1


def _sync_url(url: str) -> str:
    """Converte a URL para o driver sincrono psycopg2."""
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def seed() -> None:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurada (verifique o .env).")

    engine = create_engine(_sync_url(settings.DATABASE_URL), future=True)

    with engine.begin() as conn:
        for status_id, name in DOCUMENT_STATUS:
            conn.execute(
                text(
                    "INSERT INTO document_status (status_id, name) "
                    "VALUES (:id, :name) ON CONFLICT (status_id) DO NOTHING"
                ),
                {"id": status_id, "name": name},
            )

        for status_id, name in SIGNER_STATUS:
            conn.execute(
                text(
                    "INSERT INTO signer_status (status_id, name) "
                    "VALUES (:id, :name) ON CONFLICT (status_id) DO NOTHING"
                ),
                {"id": status_id, "name": name},
            )

        print(
            f"Lookup populado: {len(DOCUMENT_STATUS)} document_status, "
            f"{len(SIGNER_STATUS)} signer_status."
        )

        _seed_admin(conn)

    engine.dispose()


def _seed_admin(conn) -> None:
    email = os.getenv("SEED_ADMIN_EMAIL")
    password = os.getenv("SEED_ADMIN_PASSWORD")
    if not email or not password:
        print(
            "Admin nao criado: defina SEED_ADMIN_EMAIL e SEED_ADMIN_PASSWORD "
            "para criar um usuario administrador."
        )
        return

    validate_password_strength(password)
    result = conn.execute(
        text(
            "INSERT INTO user_account (email, password_hash, role, is_active) "
            "VALUES (:email, :hash, :role, true) "
            "ON CONFLICT (email) DO NOTHING RETURNING user_id"
        ),
        {"email": email, "hash": hash_password(password), "role": ROLE_ADMIN},
    )
    if result.first():
        print(f"Admin criado: {email}")
    else:
        print(f"Admin ja existia (email {email}); nada alterado.")


if __name__ == "__main__":
    seed()
