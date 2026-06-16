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
import json
import re
import uuid

from sqlalchemy import select
from app.db import get_db
from app.utils.timing import log_duration
from app.schemas.document import CreateDocument, UpdateDocument, SignerInput
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


def _validate_document_file(document_file: UploadFile):
    if not document_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo do documento é obrigatório."
        )
    if document_file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo do documento deve ser um PDF."
        )


def _validate_photo_file(photo_file: UploadFile, signer_name: str):
    if not photo_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Foto do signatário {signer_name} é obrigatória."
        )
    if photo_file.content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Foto do signatário {signer_name} deve ser JPG, PNG ou WEBP."
        )


def _validate_signer_payload(signer: dict):
    missing = [
        field for field in ("full_name", "phone_number", "email", "national_id")
        if not str(signer.get(field) or "").strip()
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campos obrigatórios do signatário: {', '.join(missing)}"
        )

    email = str(signer["email"]).strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"E-mail inválido para {signer['full_name']}."
        )

    national_id_digits = re.sub(r"\D", "", str(signer["national_id"]))
    if len(national_id_digits) != 11:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CPF inválido para {signer['full_name']}: informe 11 dígitos."
        )

    phone_digits = re.sub(r"\D", "", str(signer["phone_number"]))
    if len(phone_digits) < 10 or len(phone_digits) > 13:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telefone inválido para {signer['full_name']}: informe DDD e número."
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
    err(400, "Dados inválidos", "Campos obrigatórios do signatário: full_name, email.") |
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
    signers: str = Form(
        ...,
        description='Lista JSON de signatários: [{"full_name","phone_number","email","national_id"}]',
    ),
    document_file: UploadFile = File(...),
    signer_photos: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role not in (Role.ADMIN, Role.COMPANY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para criar documentos."
        )

    try:
        signers_data = json.loads(signers)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campo 'signers' deve ser um JSON válido."
        )
    if not isinstance(signers_data, list) or not signers_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe ao menos um signatário em 'signers'."
        )
    if len(signer_photos) != len(signers_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie uma foto para cada signatário, na mesma ordem da lista."
        )

    _validate_document_file(document_file)
    for signer in signers_data:
        _validate_signer_payload(signer)

    if current_user.role == Role.COMPANY:
        result = await db.execute(
            select(Company).where(
                Company.company_id == company_id,
                Company.user_id == current_user.user_id,
                Company.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
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
        if result.scalar_one_or_none() is None:
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

    with log_duration(logger, "Cálculo do Hash do Documento", file_name=document_file.filename, size_bytes=len(doc_bytes)):
        hash_sha256 = hashlib.sha256(doc_bytes).hexdigest()

    # Uma foto por signatário (mesma ordem da lista), gravadas só após validar.
    signer_inputs: list[SignerInput] = []
    photos_to_write: list[tuple[Path, bytes]] = []
    for signer, photo in zip(signers_data, signer_photos):
        _validate_photo_file(photo, str(signer["full_name"]))
        photo_bytes = await _read_upload_with_limit(
            photo,
            MAX_PHOTO_FILE_SIZE,
            f"foto de {signer['full_name']}"
        )
        photo_path = upload_dir / f"{uuid.uuid4()}-{photo.filename}"
        photos_to_write.append((photo_path, photo_bytes))
        signer_inputs.append(SignerInput(
            full_name=str(signer["full_name"]).strip(),
            phone_number=str(signer["phone_number"]).strip(),
            email=str(signer["email"]).strip(),
            national_id=re.sub(r"\D", "", str(signer["national_id"])),
            photo_id_url=str(photo_path),
        ))

    create_request = CreateDocument(
        company_id=company_id,
        status_id=DOCUMENT_STATUS_IN_PROGRESS,
        file_name=document_file.filename,
        file_path=str(doc_path),
        hash_sha256=hash_sha256,
        signers=signer_inputs,
    )

    try:
        with log_duration(logger, "Upload de PDF (gravação em disco)", path=str(doc_path)):
            doc_path.write_bytes(doc_bytes)
        for photo_path, photo_bytes in photos_to_write:
            photo_path.write_bytes(photo_bytes)

        document = await asyncio.wait_for(
            document_service.create_document_with_signers(db, create_request),
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
