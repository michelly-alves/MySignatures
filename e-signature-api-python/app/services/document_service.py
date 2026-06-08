import logging
import secrets
import string
import re
import uuid
from datetime import datetime, timedelta, timezone

_log = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import insert

from app.models.document import Document
from app.schemas.document import CreateDocument, UpdateDocument
from app.models.document_signer import DocumentSigner
from app.models.document_status import DocumentStatus
from app.models.user import User, Role
from app.models.signer import Signer
from app.models.company import Company
from app.models.auth_models import NotificationToken
from app.core.config import settings
from app.security.password import hash_password
from app.security.jwt import create_notification_jwt
from app.utils.email import send_pending_document_email, send_set_password_email
from app.services.face_recognition import extract_face_embedding_from_bytes, extract_face_embedding_from_path


def generate_secure_token(length: int = 32) -> str:
    return ''.join(secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(length))


async def create_document_and_signer(
    db: AsyncSession,
    new_document: CreateDocument
) -> Document:
    if not new_document.company_id:
        raise ValueError("company_id é obrigatório")
    if not new_document.file_name:
        raise ValueError("Nome do arquivo do documento é obrigatório")
    if not new_document.file_path:
        raise ValueError("Caminho do arquivo do documento é obrigatório")
    if not new_document.hash_sha256:
        raise ValueError("Hash SHA-256 do documento é obrigatório")
    if not new_document.signer_email:
        raise ValueError("signer_email é obrigatório")
    if not new_document.signer_full_name:
        raise ValueError("signer_full_name é obrigatório")
    if not new_document.signer_phone_number:
        raise ValueError("signer_phone_number é obrigatório")
    if not new_document.signer_national_id:
        raise ValueError("signer_national_id é obrigatório")

    signer_national_id = re.sub(r"\D", "", new_document.signer_national_id)
    if len(signer_national_id) != 11:
        raise ValueError("CPF do signatário inválido: informe 11 dígitos")

    result = await db.execute(
        select(Company).where(
            Company.company_id == new_document.company_id,
            Company.deleted_at.is_(None),
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError("Empresa informada não foi encontrada")

    result = await db.execute(
        select(Document).where(
            Document.hash_sha256 == new_document.hash_sha256,
            Document.company_id == new_document.company_id,
            Document.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none():
        raise ValueError("Este documento já foi cadastrado para esta empresa")

    result = await db.execute(
        select(User).where(User.email == new_document.signer_email)
    )
    user = result.scalar_one_or_none()
    user_was_created = user is None
    if user and user.role != Role.SIGNER:
        raise ValueError("O e-mail informado já pertence a um usuário que não é signatário")

    if not user:
        user = User(
            email=new_document.signer_email,
            password_hash=None,  
            role=2  # SIGNER
        )
        db.add(user)
        await db.flush()

    result = await db.execute(
        select(Signer)
        .where(Signer.national_id == signer_national_id)
        .where(Signer.deleted_at.is_(None))
        .order_by(Signer.signer_id.desc())
    )
    signer = result.scalars().first()
    if signer and signer.user_id != user.user_id:
        raise ValueError("O CPF informado já pertence a outro signatário")

    if not signer:
        signer = Signer(
            full_name=new_document.signer_full_name,
            phone_number=new_document.signer_phone_number,
            contact_email=new_document.signer_email,
            national_id=signer_national_id,
            photo_id_url=new_document.photo_id_url,
            user_id=user.user_id
        )
        db.add(signer)
        await db.flush()
        
    if signer.face_embedding is None:
        if not new_document.photo_id_url:
            raise ValueError("Foto do signatário é obrigatória para biometria")

        try:
            embedding = extract_face_embedding_from_path(new_document.photo_id_url)
            signer.face_embedding = embedding.tolist()
        except Exception as e:
            raise ValueError(f"Erro ao gerar biometria facial: {str(e)}")        

    document = Document(
        company_id=new_document.company_id,
        file_name=new_document.file_name,
        file_path=new_document.file_path,
        hash_sha256=new_document.hash_sha256,
        status_id=new_document.status_id
    )
    db.add(document)
    await db.flush()

    document_signer = DocumentSigner(
        document_id=document.document_id,
        signer_id=signer.signer_id,
        status_id=1
    )
    db.add(document_signer)

    jti = str(uuid.uuid4())
    token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=48)
    notification_jwt = create_notification_jwt(str(user.user_id), jti)

    db.add(NotificationToken(
        jti=jti,
        user_id=user.user_id,
        expires_at=token_expires_at,
    ))

    await db.commit()
    await db.refresh(document)

    try:
        if user_was_created:
            activation_link = (
                f"{settings.FRONTEND_BASE_URL}/auth/set-password?token={notification_jwt}"
            )
            send_set_password_email(
                to_email=user.email,
                full_name=signer.full_name,
                reset_link=activation_link,
            )
        else:
            documents_link = (
                f"{settings.FRONTEND_BASE_URL}/documents?token={notification_jwt}"
            )
            send_pending_document_email(
                to_email=user.email,
                full_name=signer.full_name,
                document_name=document.file_name,
                documents_link=documents_link,
            )
    except Exception as exc:
        _log.error(
            "Documento %s criado mas e-mail falhou para %s: %s",
            document.document_id,
            user.email,
            exc,
        )

    return document

async def get_all_documents(db: AsyncSession):

    result = await db.execute(
        select(Document)
        .where(Document.deleted_at.is_(None))
        .order_by(Document.document_id)
    )
    return result.scalars().all()

async def get_documents_by_user(db: AsyncSession, user: User):
    if user.role == Role.ADMIN:
        return await get_all_documents(db)

    if user.role == 0: 
        stmt = (
            select(Document)
            .join(Company, Document.company_id == Company.company_id)
            .where(Company.user_id == user.user_id)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.document_id.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    elif user.role == 2:
        stmt = (
            select(Document)
            .join(DocumentSigner, Document.document_id == DocumentSigner.document_id)
            .join(Signer, DocumentSigner.signer_id == Signer.signer_id)
            .where(Signer.user_id == user.user_id)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.document_id.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    return []

async def get_document_by_id(
    db: AsyncSession,
    document_id: int
):
    result = await db.execute(
        select(Document)
        .where(Document.document_id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()

async def can_user_access_document(
    db: AsyncSession,
    user: User,
    document_id: int
) -> bool:
    if user.role == Role.ADMIN:
        return True

    if user.role == Role.COMPANY:
        result = await db.execute(
            select(Document.document_id)
            .join(Company, Document.company_id == Company.company_id)
            .where(Document.document_id == document_id)
            .where(Document.deleted_at.is_(None))
            .where(Company.user_id == user.user_id)
        )
        return result.scalar_one_or_none() is not None

    if user.role == Role.SIGNER:
        result = await db.execute(
            select(Document.document_id)
            .join(DocumentSigner, Document.document_id == DocumentSigner.document_id)
            .join(Signer, DocumentSigner.signer_id == Signer.signer_id)
            .where(Document.document_id == document_id)
            .where(Document.deleted_at.is_(None))
            .where(Signer.user_id == user.user_id)
        )
        return result.scalar_one_or_none() is not None

    return False

async def can_user_manage_document(
    db: AsyncSession,
    user: User,
    document_id: int
) -> bool:
    if user.role == Role.ADMIN:
        return True

    if user.role != Role.COMPANY:
        return False

    result = await db.execute(
        select(Document.document_id)
        .join(Company, Document.company_id == Company.company_id)
        .where(Document.document_id == document_id)
        .where(Document.deleted_at.is_(None))
        .where(Company.user_id == user.user_id)
    )
    return result.scalar_one_or_none() is not None

async def update_document(
    db: AsyncSession,
    document_id: int,
    data: UpdateDocument
):
    document = await get_document_by_id(db, document_id)
    if not document:
        return None

    if data.file_name:
        document.file_name = data.file_name
    if data.status_id is not None:
        document.status_id = data.status_id

    document.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(document)
    return document


async def delete_document(
    db: AsyncSession,
    document_id: int
) -> bool:
    document = await get_document_by_id(db, document_id)
    if not document:
        return False

    deleted_at = datetime.utcnow()
    document.updated_at = deleted_at
    document.deleted_at = deleted_at
    await db.commit()
    return True
