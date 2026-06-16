import asyncio
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accumulator import AccumulatorElement, AccumulatorState, Witness
from app.models.audit_log import AuditLog
from app.models.digital_signature import DigitalSignature
from app.models.document import Document
from app.models.document_signer import DocumentSigner
from app.models.signer import Signer
from app.models.signer_status import SignerStatus
from app.models.user import User
from app.core.config import settings
from app.schemas.signature import SignDocumentRequest
from app.services.accumulator_service import accumulate_signature, verify_membership
from app.services.pdf_seal_service import create_signed_pdf_seal
from app.utils.hashing import compute_file_sha256
from app.utils.timing import log_duration


logger = logging.getLogger(__name__)

SIGNED_DOCUMENT_STATUS = 3
DOCUMENT_STATUS_IN_PROGRESS = 2
SIGNED_SIGNER_STATUS = SignerStatus.SIGNED.value  # = 4


def _same_public_key(pem_a: str, pem_b: str) -> bool:
    """
    Compara duas chaves públicas pelo conteúdo criptográfico (DER do
    SubjectPublicKeyInfo), tolerando diferenças de formatação do PEM
    (quebras de linha, espaços). Retorna False se qualquer uma for inválida.
    """
    try:
        key_a = serialization.load_pem_public_key(pem_a.encode("utf-8"))
        key_b = serialization.load_pem_public_key(pem_b.encode("utf-8"))
        der_a = key_a.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        der_b = key_b.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return der_a == der_b
    except Exception:
        return False


def _verify_rsa_signature(public_key_pem: str, document_hash: str, signature_base64: str) -> None:
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        signature = base64.b64decode(signature_base64, validate=True)
    except Exception as exc:
        raise ValueError("Chave pública ou assinatura em Base64 inválida") from exc

    try:
        with log_duration(logger, "Verificação da Assinatura (API)"):
            public_key.verify(
                signature,
                document_hash.encode("ascii"),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=32,
                ),
                hashes.SHA256(),
            )
    except InvalidSignature as exc:
        raise ValueError("Assinatura digital inválida para o hash do documento") from exc


def _build_signature_audit_description(
    document: Document,
    signer: Signer,
    signature: DigitalSignature,
    state: AccumulatorState,
    witness: Witness,
) -> str:
    return (
        f"Documento assinado. "
        f"document_id={document.document_id}; "
        f"signer_id={signer.signer_id}; "
        f"signature_id={signature.signature_id}; "
        f"document_hash={document.hash_sha256}; "
        f"accumulator_state_id={state.state_id}; "
        f"witness_id={witness.witness_id}"
    )


async def _get_signer_for_user(db: AsyncSession, user: User) -> Signer | None:
    result = await db.execute(
        select(Signer)
        .where(Signer.user_id == user.user_id, Signer.deleted_at.is_(None))
        .order_by(Signer.signer_id.desc())
    )
    return result.scalars().first()


def _new_validation_code() -> str:
    return f"SIG-{secrets.token_hex(16).upper()}"


def canonical_signed_at_iso(dt: datetime) -> str:
    """
    Representação canônica de signed_at usada como ingrediente do hash
    composto. Garante timezone explícito (UTC quando ausente), evitando
    inconsistências entre a string hasheada na criação e a exibida na
    verificação.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _build_event_hash(
    document_hash: str,
    signer_id: int,
    signature_id: int,
    signed_at: datetime,
) -> str:
    """
    Hash criptograficamente distinguível do evento de assinatura.

    Combina o hash do documento com identificadores únicos da operação
    (signer_id, signature_id, timestamp ISO 8601 canônico), garantindo
    que cada assinatura — mesmo sobre o mesmo documento — produza um
    elemento `x` distinto no acumulador. Preserva o invariante de primos
    únicos do esquema Baric & Pfitzmann (1997).

    Os identificadores internos (signer_id, signature_id) compõem o hash
    mas NÃO são expostos no endpoint público; a verificação externa de
    pertencimento usa diretamente o valor `x` derivado do hash, sem
    necessidade de reproduzir o hash composto.
    """
    signed_at_iso = canonical_signed_at_iso(signed_at)
    payload = f"{document_hash}|{signer_id}|{signature_id}|{signed_at_iso}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _gather_seal_entries(db: AsyncSession, document_id: int) -> list[dict]:
    """
    Dados de todos os signatários que já assinaram o documento, em ordem de
    assinatura — usados para carimbar o selo consolidado do PDF final.
    """
    result = await db.execute(
        select(DigitalSignature, Signer)
        .join(Signer, Signer.signer_id == DigitalSignature.signer_id)
        .where(DigitalSignature.doc_sign_id == document_id)
        .order_by(DigitalSignature.signature_id)
    )
    return [
        {
            "full_name": signer.full_name,
            "signed_at": signature.signed_at,
            "validation_code": signature.validation_code,
            "validation_url": signature.validation_url,
        }
        for signature, signer in result.all()
    ]


async def sign_document(
    db: AsyncSession,
    user: User,
    document_id: int,
    payload: SignDocumentRequest,
    ip_address: str | None = None,
):
    if user.otp_verified_at is None:
        raise ValueError("Valide o OTP antes de assinar documentos")

    signer = await _get_signer_for_user(db, user)
    if not signer:
        raise LookupError("Signatário não encontrado")

    result = await db.execute(
        select(DocumentSigner)
        .where(
            DocumentSigner.document_id == document_id,
            DocumentSigner.signer_id == signer.signer_id,
        )
    )
    document_signer = result.scalar_one_or_none()
    if not document_signer:
        raise PermissionError("Documento não pertence ao signatário autenticado")

    if document_signer.status_id == SIGNED_SIGNER_STATUS:
        raise ValueError("Você já assinou este documento.")

    if document_signer.status_id != SignerStatus.IDENTITY_VERIFIED.value:
        raise ValueError("Realize a verificação facial antes de assinar")

    result = await db.execute(
        select(Document).where(
            Document.document_id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise LookupError("Documento não encontrado")

    with log_duration(
        logger,
        "Reverificação do Hash do Arquivo (pré-assinatura)",
        document_id=document_id,
    ):
        actual_file_hash = await asyncio.to_thread(
            compute_file_sha256, document.file_path
        )
    if actual_file_hash is None:
        raise ValueError(
            "Arquivo original do documento não encontrado para verificação "
            "de integridade. Assinatura abortada."
        )
    if actual_file_hash != document.hash_sha256:
        logger.error(
            "Integridade violada antes da assinatura: hash do arquivo em disco "
            "difere do registrado. document_id=%s registrado=%s atual=%s",
            document_id,
            document.hash_sha256,
            actual_file_hash,
        )
        raise ValueError(
            "Integridade violada: o arquivo do documento em disco não "
            "corresponde ao hash registrado no upload. Assinatura abortada."
        )

    registered_pem = signer.public_key
    provided_pem = payload.public_key_pem

    if registered_pem:
        if provided_pem and not _same_public_key(provided_pem, registered_pem):
            raise ValueError(
                "A chave pública usada na assinatura não corresponde à chave "
                "registrada do signatário."
            )
        public_key_pem = registered_pem
    else:
        if not provided_pem:
            raise ValueError("Chave pública do signatário não informada")
        public_key_pem = provided_pem

    _verify_rsa_signature(
        public_key_pem=public_key_pem,
        document_hash=document.hash_sha256,
        signature_base64=payload.signature_base64,
    )

    if not signer.public_key:
        signer.public_key = public_key_pem

    digital_signature = DigitalSignature(
        doc_sign_id=document_id,
        signer_id=signer.signer_id,
        signature_data=payload.signature_base64,
        public_key_pem=public_key_pem,  
        ip_address=ip_address,
        validation_code=_new_validation_code(),
    )

    digital_signature.validation_url = (
        f"{settings.FRONTEND_BASE_URL}/validate?code={digital_signature.validation_code}"
    )
    db.add(digital_signature)
    await db.flush()
    await db.refresh(digital_signature)

    event_hash = _build_event_hash(
        document_hash=document.hash_sha256,
        signer_id=signer.signer_id,
        signature_id=digital_signature.signature_id,
        signed_at=digital_signature.signed_at,
    )

    with log_duration(
        logger,
        "Acumulação do Evento de Assinatura",
        document_id=document.document_id,
        signature_id=digital_signature.signature_id,
    ):
        accumulator = await accumulate_signature(
            db=db,
            document_id=document.document_id,
            signature_id=digital_signature.signature_id,
            hash_hex=event_hash,
            created_by=user.user_id,
        )

    document_signer.status_id = SIGNED_SIGNER_STATUS
    document_signer.verified_at = document_signer.verified_at or datetime.utcnow()
    document.updated_at = datetime.utcnow()

    await db.flush()

    pending_signers = await db.scalar(
        select(func.count())
        .select_from(DocumentSigner)
        .where(
            DocumentSigner.document_id == document_id,
            DocumentSigner.status_id != SIGNED_SIGNER_STATUS,
        )
    )
    all_signed = pending_signers == 0

    document.status_id = SIGNED_DOCUMENT_STATUS if all_signed else DOCUMENT_STATUS_IN_PROGRESS

    if all_signed:
        seal_entries = await _gather_seal_entries(db, document_id)
        try:
            with log_duration(
                logger,
                "Geração do PDF Selado (consolidado)",
                document_id=document.document_id,
                signature_id=digital_signature.signature_id,
            ):
                digital_signature.signed_file_path = create_signed_pdf_seal(
                    document=document,
                    entries=seal_entries,
                    state=accumulator.state,
                    previous_state=accumulator.previous_state,
                )
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

        digital_signature.signed_file_sha256 = await asyncio.to_thread(
            compute_file_sha256, digital_signature.signed_file_path
        )

    audit_description = _build_signature_audit_description(
        document=document,
        signer=signer,
        signature=digital_signature,
        state=accumulator.state,
        witness=accumulator.witness,
    )
    db.add_all([
        AuditLog(
            user_id=user.user_id,
            entity_name="document",
            entity_id=document.document_id,
            action="DOCUMENT_SIGNED",
            description=audit_description,
            ip_address=ip_address,
        ),
        AuditLog(
            user_id=user.user_id,
            entity_name="signer",
            entity_id=signer.signer_id,
            action="SIGNER_SIGNED_DOCUMENT",
            description=audit_description,
            ip_address=ip_address,
        ),
    ])

    await db.commit()
    await db.refresh(digital_signature)
    await db.refresh(accumulator.state)
    await db.refresh(accumulator.element)
    await db.refresh(accumulator.witness)

    return {
        "document": document,
        "signer": signer,
        "signature": digital_signature,
        "state": accumulator.state,
        "element": accumulator.element,
        "witness": accumulator.witness,
    }


async def get_signature_proof(db: AsyncSession, user: User, document_id: int):
    result = await db.execute(
        select(DigitalSignature, AccumulatorElement, AccumulatorState, Witness, Signer)
        .join(AccumulatorElement, AccumulatorElement.signature_id == DigitalSignature.signature_id)
        .join(Witness, Witness.element_id == AccumulatorElement.element_id)
        .join(AccumulatorState, AccumulatorState.state_id == Witness.state_id)
        .join(Signer, Signer.signer_id == DigitalSignature.signer_id)
        .where(AccumulatorElement.document_id == document_id)
        .order_by(DigitalSignature.signature_id.desc(), Witness.state_id.desc())
    )
    row = result.first()
    if not row:
        return None

    signature, element, state, witness, signer = row
    witness_valid = verify_membership(
        witness_hex=witness.witness_value_hex,
        x_value_hex=element.x_value_hex,
        state_value_hex=state.state_value_hex,
        modulus_n_hex=state.modulus_n_hex,
    )

    return {
        "signature": signature,
        "element": element,
        "state": state,
        "witness": witness,
        "signer": signer,
        "public_key_pem": signature.public_key_pem or signer.public_key,
        "witness_valid": witness_valid,
    }


async def get_signature_proof_by_validation_code(db: AsyncSession, validation_code: str):
    result = await db.execute(
        select(DigitalSignature, AccumulatorElement, AccumulatorState, Witness, Signer, Document)
        .join(AccumulatorElement, AccumulatorElement.signature_id == DigitalSignature.signature_id)
        .join(Witness, Witness.element_id == AccumulatorElement.element_id)
        .join(AccumulatorState, AccumulatorState.state_id == Witness.state_id)
        .join(Signer, Signer.signer_id == DigitalSignature.signer_id)
        .join(Document, Document.document_id == AccumulatorElement.document_id)
        .where(DigitalSignature.validation_code == validation_code)
        .order_by(Witness.state_id.desc())
    )
    row = result.first()
    if not row:
        return None

    signature, element, state, witness, signer, document = row
    witness_valid = verify_membership(
        witness_hex=witness.witness_value_hex,
        x_value_hex=element.x_value_hex,
        state_value_hex=state.state_value_hex,
        modulus_n_hex=state.modulus_n_hex,
    )

    return {
        "signature": signature,
        "element": element,
        "state": state,
        "witness": witness,
        "signer": signer,
        "document": document,
        "public_key_pem": signature.public_key_pem or signer.public_key,
        "witness_valid": witness_valid,
    }


async def get_document_signature_summary(db: AsyncSession, document_id: int):
    result = await db.execute(
        select(DigitalSignature, Signer)
        .join(Signer, Signer.signer_id == DigitalSignature.signer_id)
        .where(DigitalSignature.doc_sign_id == document_id)
        .order_by(DigitalSignature.signature_id.desc())
    )
    row = result.first()
    if not row:
        return None

    signature, signer = row
    return {
        "document_id": document_id,
        "signature_id": signature.signature_id,
        "signer_id": signer.signer_id,
        "signer_name": signer.full_name,
        "signed_at": signature.signed_at,
        "validation_code": signature.validation_code,
        "validation_url": signature.validation_url,
    }


async def get_document_signers_overview(db: AsyncSession, document_id: int) -> list[dict]:
    """
    Visão de TODOS os signatários do documento e o status de cada um (quem já
    assinou e quem falta), para a validação pública. Para quem assinou, inclui
    o respectivo código de validação individual.
    """
    rows = await db.execute(
        select(DocumentSigner, Signer)
        .join(Signer, Signer.signer_id == DocumentSigner.signer_id)
        .where(DocumentSigner.document_id == document_id)
        .order_by(DocumentSigner.signer_id)
    )
    signer_rows = rows.all()

    sig_rows = await db.execute(
        select(DigitalSignature).where(DigitalSignature.doc_sign_id == document_id)
    )
    signature_by_signer = {s.signer_id: s for s in sig_rows.scalars().all()}

    overview: list[dict] = []
    for document_signer, signer in signer_rows:
        signature = signature_by_signer.get(signer.signer_id)
        overview.append({
            "signer_id": signer.signer_id,
            "full_name": signer.full_name,
            "status_id": document_signer.status_id,
            "signed_at": signature.signed_at if signature else None,
            "validation_code": signature.validation_code if signature else None,
        })
    return overview


async def get_document_by_validation_code(
    db: AsyncSession,
    validation_code: str,
) -> Document | None:
    result = await db.execute(
        select(Document)
        .join(DigitalSignature, DigitalSignature.doc_sign_id == Document.document_id)
        .where(DigitalSignature.validation_code == validation_code)
    )
    return result.scalars().first()


async def get_document_and_signature_by_validation_code(
    db: AsyncSession,
    validation_code: str,
) -> tuple[Document, DigitalSignature] | None:
    """
    Documento e respectiva assinatura digital a partir do código de validação.
    Suficiente para a verificação de integridade (hash do original em
    Document.hash_sha256 e hash do PDF selado em
    DigitalSignature.signed_file_sha256).
    """
    result = await db.execute(
        select(Document, DigitalSignature)
        .join(DigitalSignature, DigitalSignature.doc_sign_id == Document.document_id)
        .where(DigitalSignature.validation_code == validation_code)
        .order_by(DigitalSignature.signature_id.desc())
    )
    return result.first()


async def get_latest_signature_for_document(
    db: AsyncSession,
    document_id: int,
) -> DigitalSignature | None:
    result = await db.execute(
        select(DigitalSignature)
        .where(DigitalSignature.doc_sign_id == document_id)
        .order_by(DigitalSignature.signature_id.desc())
    )
    return result.scalars().first()
