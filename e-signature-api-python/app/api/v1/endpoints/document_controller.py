from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Form,
    HTTPException,
    status
)
from fastapi.responses import Response
from urllib.parse import quote
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import hashlib
import re
import uuid

from sqlalchemy import select
from app.db import get_db
from app.utils.timing import log_duration
from app.schemas.document import CreateDocument, UpdateDocument
from app.services import document_service
from app.services.signature_service import get_latest_signature_for_document
from app.security.roles import require_roles
from app.models.user import Role
from app.models.user import User
from app.models.company import Company
from app.dependencies.auth import get_current_user
from app.api.v1.responses import err, _401, _422, _500

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 30
MAX_DOCUMENT_FILE_SIZE = 10 * 1024 * 1024
MAX_PHOTO_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_STATUS_IN_PROGRESS = 2


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_required_document_fields(
    company_id: int,
    status_id: int,
    signer_full_name: str | None,
    signer_phone_number: str | None,
    signer_email: str | None,
    signer_national_id: str | None,
):
    missing = []

    if not company_id or company_id <= 0:
        missing.append("company_id")
    if not status_id or status_id <= 0:
        missing.append("status_id")
    if not signer_full_name:
        missing.append("signer_full_name")
    if not signer_phone_number:
        missing.append("signer_phone_number")
    if not signer_email:
        missing.append("signer_email")
    if not signer_national_id:
        missing.append("signer_national_id")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campos obrigatórios para criação do documento: {', '.join(missing)}"
        )

    national_id_digits = re.sub(r"\D", "", signer_national_id)
    if len(national_id_digits) != 11:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CPF do signatário inválido: informe 11 dígitos em signer_national_id."
        )

    phone_digits = re.sub(r"\D", "", signer_phone_number)
    if len(phone_digits) < 10 or len(phone_digits) > 13:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telefone do signatário inválido: informe DDD e número em signer_phone_number."
        )


def _validate_upload_metadata(
    document_file: UploadFile,
    signer_photo_id_file: UploadFile,
):
    if not document_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo do documento é obrigatório."
        )
    if not signer_photo_id_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Foto do documento/selfie do signatário é obrigatória."
        )
    if document_file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo do documento deve ser um PDF."
        )
    if signer_photo_id_file.content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Foto do signatário deve ser JPG, PNG ou WEBP."
        )


async def _read_upload_with_limit(
    file: UploadFile,
    max_size: int,
    field_name: str
) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O arquivo '{field_name}' está vazio."
        )
    if len(content) > max_size:
        max_mb = max_size // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"O arquivo '{field_name}' excede o limite de {max_mb}MB."
        )
    return content


@router.post("", status_code=status.HTTP_201_CREATED, responses=(
    err(400, "Dados inválidos", "Campos obrigatórios para criação do documento: signer_full_name, signer_email.") |
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para criar documentos.") |
    err(404, "Empresa não encontrada", "Empresa informada não foi encontrada.") |
    err(413, "Arquivo muito grande", "O arquivo 'document_file' excede o limite de 10MB.") |
    _422 |
    _500 |
    err(504, "Timeout", "Tempo limite de 30 segundos atingido ao criar o documento.")
))
async def create_document(
    current_user: User = Depends(get_current_user),
    company_id: int = Form(...),
    status_id: int = Form(2),

    signer_full_name: str | None = Form(None),
    signer_phone_number: str | None = Form(None),
    signer_email: str | None = Form(None),
    signer_national_id: str | None = Form(None),

    document_file: UploadFile = File(...),
    signer_photo_id_file: UploadFile = File(...),

    db: AsyncSession = Depends(get_db)
):
    signer_full_name = _strip_optional(signer_full_name)
    signer_phone_number = _strip_optional(signer_phone_number)
    signer_email = _strip_optional(signer_email)
    signer_national_id = _strip_optional(signer_national_id)

    _validate_required_document_fields(
        company_id=company_id,
        status_id=status_id,
        signer_full_name=signer_full_name,
        signer_phone_number=signer_phone_number,
        signer_email=signer_email,
        signer_national_id=signer_national_id,
    )
    _validate_upload_metadata(document_file, signer_photo_id_file)

    if current_user.role not in (Role.ADMIN, Role.COMPANY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para criar documentos."
        )

    if current_user.role == Role.COMPANY:
        result = await db.execute(
            select(Company).where(
                Company.company_id == company_id,
                Company.user_id == current_user.user_id,
                Company.deleted_at.is_(None),
            )
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Empresa informada não pertence ao usuário autenticado."
            )

    if current_user.role == Role.ADMIN:
        result = await db.execute(
            select(Company).where(
                Company.company_id == company_id,
                Company.deleted_at.is_(None),
            )
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa informada não foi encontrada."
            )

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    doc_filename = f"{uuid.uuid4()}-{document_file.filename}"
    doc_path = upload_dir / doc_filename
    with log_duration(logger, "Upload de PDF (recepção)", file_name=document_file.filename):
        doc_bytes = await _read_upload_with_limit(
            document_file,
            MAX_DOCUMENT_FILE_SIZE,
            "document_file"
        )

    photo_filename = f"{uuid.uuid4()}-{signer_photo_id_file.filename}"
    photo_path = upload_dir / photo_filename
    photo_bytes = await _read_upload_with_limit(
        signer_photo_id_file,
        MAX_PHOTO_FILE_SIZE,
        "signer_photo_id_file"
    )

    with log_duration(logger, "Cálculo do Hash do Documento", file_name=document_file.filename, size_bytes=len(doc_bytes)):
        hash_sha256 = hashlib.sha256(doc_bytes).hexdigest()
    signer_national_id = re.sub(r"\D", "", signer_national_id)
    status_id = DOCUMENT_STATUS_IN_PROGRESS

    create_request = CreateDocument(
        company_id=company_id,
        status_id=status_id,
        signer_full_name=signer_full_name,
        signer_phone_number=signer_phone_number,
        signer_email=signer_email,
        signer_national_id=signer_national_id,
        file_name=document_file.filename,
        file_path=str(doc_path),
        hash_sha256=hash_sha256,
        photo_id_url=str(photo_path)
    )

    try:
        with log_duration(logger, "Upload de PDF (gravação em disco)", path=str(doc_path)):
            doc_path.write_bytes(doc_bytes)
        photo_path.write_bytes(photo_bytes)

        document = await asyncio.wait_for(
            document_service.create_document_and_signer(db, create_request),
            timeout=TIMEOUT_SECONDS
        )
        return document
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Tempo limite de {TIMEOUT_SECONDS} segundos atingido ao criar o documento."
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao criar documento: {e}"
        )
        
        
@router.get("", responses=_401 | _500)
async def list_documents(
    current_user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    return await document_service.get_documents_by_user(db, current_user)


@router.get("/{document_id}/file", responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para visualizar este documento.") |
    err(404, "Não encontrado", "Documento não encontrado.") |
    _500
))
async def get_document_file(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    allowed = await document_service.can_user_access_document(
        db,
        current_user,
        document_id
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para visualizar este documento."
        )

    document = await document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado"
        )

    signature = await get_latest_signature_for_document(db, document_id)
    file_path = signature.signed_file_path if signature and signature.signed_file_path else document.file_path
    document_path = Path(file_path)
    if not document_path.exists() or not document_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do documento não encontrado"
        )

    with log_duration(
        logger,
        "Download de PDF (leitura do arquivo em disco)",
        document_id=document_id,
        path=str(document_path),
        size_bytes=document_path.stat().st_size,
    ):
        file_bytes = document_path.read_bytes()

    disposition = f"attachment; filename*=utf-8''{quote(document.file_name)}"
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/{document_id}", responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para acessar este documento.") |
    err(404, "Não encontrado", "Documento não encontrado.") |
    _500
))
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    allowed = await document_service.can_user_access_document(
        db,
        current_user,
        document_id
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este documento."
        )

    document = await document_service.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


@router.put("/{document_id}", responses=(
    _401 |
    err(403, "Sem permissão", "Você não tem permissão para alterar este documento.") |
    err(404, "Não encontrado", "Documento não encontrado.") |
    _422 |
    _500
))
async def update_document(
    document_id: int,
    payload: UpdateDocument,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    allowed = await document_service.can_user_manage_document(
        db,
        current_user,
        document_id
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para alterar este documento."
        )

    document = await document_service.update_document(
        db, document_id, payload
    )
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document

@router.delete("/{document_id}", responses=(
    _401 |
    err(403, "Sem permissão", "Apenas administradores podem remover documentos.") |
    err(404, "Não encontrado", "Documento não encontrado.") |
    _500
))
async def delete_document(
    document_id: int,
    current_user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db)
):
    deleted = await document_service.delete_document(db, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {"message": "Documento removido com sucesso"}
