import asyncio
import logging
import secrets
import string
import re
import uuid
from datetime import datetime, timedelta, timezone

_log = logging.getLogger(__name__)

EMAIL_MAX_ATTEMPTS = 3
EMAIL_RETRY_DELAY_SECONDS = 2


async def _send_with_retry(send_fn, *, email: str, document_id: int, email_kind: str) -> bool:
    """Tenta enviar um e-mail algumas vezes. Retorna True se enviou, False caso contrário."""
    for attempt in range(1, EMAIL_MAX_ATTEMPTS + 1):
        try:
            await asyncio.to_thread(send_fn)
            return True
        except Exception as exc:
            _log.warning(
                "Falha ao enviar e-mail '%s' para %s (documento %s) tentativa %d/%d: %s",
                email_kind,
                email,
                document_id,
                attempt,
                EMAIL_MAX_ATTEMPTS,
                exc,
            )
            if attempt < EMAIL_MAX_ATTEMPTS:
                await asyncio.sleep(EMAIL_RETRY_DELAY_SECONDS)
    return False

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
from app.services.face_recognition import extract_face_embedding_from_bytes, extract_enrollment_embedding


def generate_secure_token(length: int = 32) -> str:
    return ''.join(secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(length))


async def create_document_with_signers(
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
    if not new_document.signers:
        raise ValueError("Informe ao menos um signatário")

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

    # Normaliza/valida cada signatário e detecta CPFs repetidos na própria lista.
    normalized: list[tuple] = []
    seen_ids: set[str] = set()
    for input_signer in new_document.signers:
        if not input_signer.full_name:
            raise ValueError("Nome do signatário é obrigatório")
        if not input_signer.email:
            raise ValueError("E-mail do signatário é obrigatório")
        if not input_signer.phone_number:
            raise ValueError("Telefone do signatário é obrigatório")

        national_id = re.sub(r"\D", "", input_signer.national_id or "")
        if len(national_id) != 11:
            raise ValueError(
                f"CPF inválido para {input_signer.full_name}: informe 11 dígitos"
            )
        if national_id in seen_ids:
            raise ValueError("Há CPFs repetidos na lista de signatários")
        seen_ids.add(national_id)
        normalized.append((input_signer, national_id))

    # Cria o documento uma única vez.
    document = Document(
        company_id=new_document.company_id,
        file_name=new_document.file_name,
        file_path=new_document.file_path,
        hash_sha256=new_document.hash_sha256,
        status_id=new_document.status_id
    )
    db.add(document)
    await db.flush()

    # Vincula cada signatário; os e-mails são enviados após o commit.
    pending_emails: list[dict] = []
    for input_signer, national_id in normalized:
        result = await db.execute(
            select(User).where(
                User.email == input_signer.email,
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        user_was_created = user is None
        if user and user.role != Role.SIGNER:
            raise ValueError(
                f"O e-mail {input_signer.email} já pertence a um usuário que não é signatário"
            )

        if not user:
            user = User(
                email=input_signer.email,
                password_hash=None,
                role=Role.SIGNER
            )
            db.add(user)
            await db.flush()

        result = await db.execute(
            select(Signer)
            .where(Signer.national_id == national_id)
            .where(Signer.deleted_at.is_(None))
            .order_by(Signer.signer_id.desc())
        )
        signer = result.scalars().first()
        if signer and signer.user_id != user.user_id:
            raise ValueError(
                f"O CPF informado para {input_signer.full_name} já pertence a outro signatário"
            )

        if not signer:
            signer = Signer(
                full_name=input_signer.full_name,
                phone_number=input_signer.phone_number,
                contact_email=input_signer.email,
                national_id=national_id,
                photo_id_url=input_signer.photo_id_url,
                user_id=user.user_id
            )
            db.add(signer)
            await db.flush()

        # Biometria POR DOCUMENTO: extrai sempre da foto enviada para ESTE
        # documento, mesmo que o signatário já exista. Garante que a validação
        # facial deste documento usa exatamente a foto deste registro.
        if not input_signer.photo_id_url:
            raise ValueError(
                f"Foto do signatário {input_signer.full_name} é obrigatória para biometria"
            )
        try:
            embedding = extract_enrollment_embedding(input_signer.photo_id_url)
            embedding_list = embedding.tolist()
        except Exception as e:
            raise ValueError(
                f"Erro ao gerar biometria facial de {input_signer.full_name}: {str(e)}"
            )

        # Enrollment de nível signatário só na primeira vez (referência usada em
        # fluxos não atrelados a documento, como a rotação de chave).
        if signer.face_embedding is None:
            signer.face_embedding = embedding_list

        db.add(DocumentSigner(
            document_id=document.document_id,
            signer_id=signer.signer_id,
            status_id=1,
            photo_id_url=input_signer.photo_id_url,
            face_embedding=embedding_list,
        ))

        jti = str(uuid.uuid4())
        token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=48)
        notification_jwt = create_notification_jwt(str(user.user_id), jti)
        db.add(NotificationToken(
            jti=jti,
            user_id=user.user_id,
            expires_at=token_expires_at,
        ))

        pending_emails.append({
            "user_was_created": user_was_created,
            "email": user.email,
            "full_name": signer.full_name,
            "token": notification_jwt,
        })

    await db.commit()
    await db.refresh(document)

    failed_emails: list[dict] = []
    for item in pending_emails:
        if item["user_was_created"]:
            activation_link = (
                f"{settings.FRONTEND_BASE_URL}/auth/set-password?token={item['token']}"
            )
            sent = await _send_with_retry(
                lambda item=item, link=activation_link: send_set_password_email(
                    to_email=item["email"],
                    full_name=item["full_name"],
                    reset_link=link,
                ),
                email=item["email"],
                document_id=document.document_id,
                email_kind="set-password",
            )
        else:
            documents_link = (
                f"{settings.FRONTEND_BASE_URL}/documents?token={item['token']}"
            )
            sent = await _send_with_retry(
                lambda item=item, link=documents_link: send_pending_document_email(
                    to_email=item["email"],
                    full_name=item["full_name"],
                    document_name=document.file_name,
                    documents_link=link,
                ),
                email=item["email"],
                document_id=document.document_id,
                email_kind="pending-document",
            )

        if not sent:
            failed_emails.append(item)

    if failed_emails:
        # Documento e usuários já foram persistidos; signatários novos dependem
        # deste e-mail para definir a senha. Registra de forma acionável para
        # reenvio manual/automático posterior.
        _log.error(
            "Documento %s criado, mas o envio de e-mail falhou para: %s",
            document.document_id,
            ", ".join(item["email"] for item in failed_emails),
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
