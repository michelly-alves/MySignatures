from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.models.document_signer import DocumentSigner
from app.models.document import Document
from app.models.company import Company
from app.models.signer import Signer
from app.models.user import Role, User


class DocumentSignerService:

    @staticmethod
    async def get_document_signers_for_user(
        db: AsyncSession,
        user: User,
        document_id: int | None = None,
    ) -> List[DocumentSigner]:
        query = (
            select(DocumentSigner)
            .join(Document, Document.document_id == DocumentSigner.document_id)
            .where(Document.deleted_at.is_(None))
        )

        if document_id is not None:
            query = query.where(Document.document_id == document_id)

        if user.role == Role.ADMIN:
            result = await db.execute(query)
            return result.scalars().all()

        if user.role == Role.COMPANY:
            query = query.join(Company, Document.company_id == Company.company_id)
            query = query.where(
                Company.user_id == user.user_id,
                Company.deleted_at.is_(None),
            )
            result = await db.execute(query)
            return result.scalars().all()

        if user.role == Role.SIGNER:
            query = query.join(Signer, DocumentSigner.signer_id == Signer.signer_id)
            query = query.where(
                Signer.user_id == user.user_id,
                Signer.deleted_at.is_(None),
            )
            result = await db.execute(query)
            return result.scalars().all()

        return []

    @staticmethod
    async def get_document_signers_by_company(
        db: AsyncSession,
        company_id: int,
    ) -> List[DocumentSigner]:

        query = (
            select(DocumentSigner)
            .join(
                Document,
                Document.document_id == DocumentSigner.document_id
            )
            .where(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_document_signers_by_document(
        db: AsyncSession,
        document_id: int,
        company_id: int,
    ) -> List[DocumentSigner]:

        query = (
            select(DocumentSigner)
            .join(
                Document,
                Document.document_id == DocumentSigner.document_id
            )
            .where(
                Document.document_id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        return result.scalars().all()
