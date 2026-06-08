import os
from logging.config import fileConfig
from pathlib import Path
from sqlalchemy import engine_from_config, pool
from sqlalchemy import create_engine  
from alembic import context
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL.startswith("postgresql+asyncpg"):
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
else:
    SYNC_DATABASE_URL = DATABASE_URL

config = context.config
if SYNC_DATABASE_URL:
    config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.db import Base
from app.models.user import User
from app.models.company import Company
from app.models.signer import Signer
from app.models.auth_models import ResetPasswordToken
from app.models.document import Document
from app.models.document_status import DocumentStatus
from app.models.document_signer import DocumentSigner
from app.models.digital_signature import DigitalSignature
from app.models.audit_log import AuditLog
from app.models.accumulator import (
    AccumulatorState,
    AccumulatorElement,
    AccumulatorElementState,
    Witness,
    PublicAccumulatorRegistry,
)
from app.models.signer_status import SignerStatusModel
from app.models.otp_codes import OtpCode
from app.models.auth_log import AuthLog
from app.models.identity_document import IdentityDocument

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Executa migrações em modo offline."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Executa migrações em modo online."""
    connectable = create_engine(
        SYNC_DATABASE_URL,
        poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
