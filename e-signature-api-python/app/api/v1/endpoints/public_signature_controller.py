import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import document_service, signature_service
from app.utils.hashing import compute_file_sha256
from app.api.v1.responses import err, _401, _500

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/signatures", tags=["Public Signatures"])

_BRT = timezone(timedelta(hours=-3))

_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

_MAX_VERIFY_FILE_SIZE = 10 * 1024 * 1024 

_SIGNER_STATUS_LABELS = {
    1: "Aguardando assinatura",
    2: "Identidade verificada — falta assinar",
    3: "Falha na verificação de identidade",
    4: "Assinou",
}


def _mask_signer_name(full_name: str | None) -> str:
    """
    Mascara o nome para o endpoint público preservando apenas o primeiro
    nome e a inicial do último sobrenome.

    Exemplos:
        'Michelly Alves Oliveira Silva' -> 'Michelly S***'
        'Joao Souza'                    -> 'Joao S***'
        'Ana'                           -> 'An***'
    """
    if not full_name:
        return ""
    parts = full_name.strip().split()
    if not parts:
        return ""
    if len(parts) == 1:
        first = parts[0]
        return f"{first[:2]}***" if len(first) > 2 else first
    return f"{parts[0]} {parts[-1][0]}***"


def _format_signed_at(dt: datetime | None) -> dict:
    """Retorna a data em ISO 8601 e em formato legível (horário de Brasília)."""
    if not dt:
        return {"iso": None, "formatted": "Data indisponível"}

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_brt = dt.astimezone(_BRT)

    return {
        "iso": dt.isoformat(),
        "formatted": (
            f"{dt_brt.day} de {_MONTHS_PT[dt_brt.month - 1]} de {dt_brt.year} "
            f"às {dt_brt.strftime('%H:%M')} (horário de Brasília)"
        ),
    }


def _safe_public_key_pem(pem: str | None) -> str | None:
    """Valida a chave pública PEM antes de expô-la; retorna None se malformada."""
    if not pem:
        return None
    try:
        serialization.load_pem_public_key(pem.encode("utf-8"))
        return pem
    except Exception:
        logger.error("Chave pública PEM malformada no endpoint público.")
        return None


@router.get("/{validation_code}", responses=(
    err(404, "Não encontrado", "Assinatura não encontrada.") |
    _500
))
async def validate_signature_publicly(
    validation_code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await signature_service.get_signature_proof_by_validation_code(
        db=db,
        validation_code=validation_code,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada.",
        )

    signature = result["signature"]
    element = result["element"]
    state = result["state"]
    witness = result["witness"]
    signer = result["signer"]
    document = result["document"]
    witness_valid = result["witness_valid"]

    if witness_valid is None:
        logger.error(
            "witness_valid retornado como None para validation_code=%s. "
            "Possível corrupção de dados ou bug no serviço de verificação.",
            validation_code,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verificação da assinatura indeterminada no momento. Tente novamente.",
        )
    is_valid = bool(witness_valid)

    if not is_valid:
        logger.error(
            "Assinatura registrada falhou na verificação criptográfica. "
            "validation_code=%s signature_id=%s state_id=%s element_id=%s witness_id=%s",
            validation_code,
            signature.signature_id,
            state.state_id,
            element.element_id,
            witness.witness_id,
        )

    signed_at_iso = (
        signature_service.canonical_signed_at_iso(signature.signed_at)
        if signature.signed_at
        else None
    )
    safe_public_key = _safe_public_key_pem(result["public_key_pem"])

    canonical_event = signature_service.build_canonical_event(
        document_hash=document.hash_sha256,
        signature_base64=signature.signature_data,
        public_key_pem=result["public_key_pem"],
        validation_code=signature.validation_code,
        signed_at=signature.signed_at,
    )

    actual_file_hash = await asyncio.to_thread(compute_file_sha256, document.file_path)
    arquivo_integro = (
        None if actual_file_hash is None
        else actual_file_hash == document.hash_sha256
    )
    if arquivo_integro is False:
        logger.error(
            "Arquivo original em disco não corresponde ao hash registrado. "
            "validation_code=%s document_id=%s",
            validation_code,
            document.document_id,
        )
    original_url = (
        f"{settings.PUBLIC_BASE_URL}/public/signatures/"
        f"{signature.validation_code}/original"
    )

    roster = await signature_service.get_document_signers_overview(
        db, document.document_id
    )
    signers_payload = [
        {
            "nome": _mask_signer_name(item["full_name"]),
            "assinou": item["status_id"] == 4,
            "status": _SIGNER_STATUS_LABELS.get(item["status_id"], "Pendente"),
            "assinado_em": (
                _format_signed_at(item["signed_at"]) if item["signed_at"] else None
            ),
            "codigo_de_validacao": item["validation_code"],
        }
        for item in roster
    ]
    signed_count = sum(1 for item in roster if item["status_id"] == 4)
    total_signers = len(roster)

    return {
        "valido": is_valid,
        "status": (
            "Assinatura válida"
            if is_valid
            else "Assinatura inválida"
        ),
        "mensagem": (
            "Esta assinatura digital foi verificada com sucesso. "
            "A integridade do documento e a prova de pertencimento ao "
            "acumulador foram confirmadas."
            if is_valid
            else "Esta assinatura não pôde ser verificada. Os dados "
                 "criptográficos podem ter sido alterados ou estão inconsistentes."
        ),
        "codigo_de_validacao": signature.validation_code,

        "signatario": {
            "nome": _mask_signer_name(signer.full_name),
            "observacao": (
                "Nome parcialmente mascarado para proteção de dados "
                "pessoais (LGPD)."
            ),
        },

        "assinado_em": _format_signed_at(signature.signed_at),

        "signatarios_do_documento": {
            "total": total_signers,
            "assinaram": signed_count,
            "todos_assinaram": total_signers > 0 and signed_count == total_signers,
            "observacao": (
                "Lista de todos os signatários deste documento e o status de "
                "cada um. Nomes parcialmente mascarados (LGPD)."
            ),
            "lista": signers_payload,
        },

        "documento": {
            "hash_sha256": document.hash_sha256,
            "algoritmo_de_hash": "SHA-256",
            "arquivo_integro_no_servidor": arquivo_integro,
            "arquivo_original_url": original_url,
            "observacao": (
                "Hash do arquivo PDF ORIGINAL, anterior à aplicação do selo "
                "visual (o PDF selado tem bytes diferentes por construção). "
                "Para conferir os bytes do arquivo, baixe o original em "
                "'arquivo_original_url' (acesso restrito: requer autenticação "
                "como empresa proprietária ou signatário do documento), "
                "calcule o SHA-256 e compare com o hash acima. "
                "'arquivo_integro_no_servidor' é a reconferência feita pelo "
                "servidor neste instante (true = arquivo em disco ainda produz "
                "o hash registrado)."
            ),
        },

        "evento_de_assinatura": {
            "descricao": (
                "O evento de assinatura é serializado de forma canônica, com "
                "separação de domínio e versão explícita, a partir EXCLUSIVAMENTE "
                "de campos públicos, e então hasheado com SHA-256. Esse hash é o "
                "que é registrado no acumulador. Um verificador externo pode "
                "reproduzir 'hash_evento' a partir dos campos abaixo e, em "
                "seguida, derivar o representante primo 'x_hex' (na prova técnica)."
            ),
            "dominio": canonical_event["dominio"],
            "versao_formato": canonical_event["versao"],
            "hash_documento": canonical_event["hash_documento"],
            "hash_assinatura": canonical_event["hash_assinatura"],
            "hash_chave_publica": canonical_event["hash_chave_publica"],
            "codigo_publico": canonical_event["codigo_publico"],
            "timestamp_iso8601": canonical_event["timestamp_iso8601"],
            "hash_evento": canonical_event["hash_evento"],
            "hash_composto_sha256": element.hash_hex,
            "hash_evento_reproduzivel": canonical_event["hash_evento"] == element.hash_hex,
            "serializacao": (
                "Para cada campo, na ordem [dominio, versao, hash_documento, "
                "hash_assinatura, hash_chave_publica, codigo_publico, "
                "timestamp_iso8601], concatene: comprimento do nome (4 bytes "
                "big-endian) ‖ nome ‖ comprimento do valor (4 bytes big-endian) "
                "‖ valor (UTF-8). hash_evento = SHA-256 dessa serialização. "
                "hash_assinatura = SHA-256 dos bytes brutos da assinatura; "
                "hash_chave_publica = SHA-256 do DER (SubjectPublicKeyInfo) da "
                "chave pública."
            ),
            "assinado_em": signed_at_iso,
        },

        "prova_tecnica": {
            "descricao": (
                "Estes campos permitem verificar a assinatura sem depender "
                "desta plataforma. A verificação combina assinatura digital "
                "RSA-PSS sobre o hash do documento e prova de pertencimento "
                "em um acumulador criptográfico RSA."
            ),
            "assinatura_rsa": {
                "algoritmo": "RSA-PSS com SHA-256, MGF1-SHA256 e salt de 32 bytes",
                "signature_base64": signature.signature_data,
                "public_key_pem": safe_public_key,
                "mensagem_assinada": (
                    "A mensagem assinada NÃO é o digest binário do documento, e sim "
                    "o 'hash_documento' como string hexadecimal minúscula de 64 "
                    "caracteres, codificada em ASCII/UTF-8. O esquema RSA-PSS aplica "
                    "SHA-256 sobre esses bytes."
                ),
                "equacao_de_verificacao": (
                    "RSA-PSS.verify(public_key_pem, "
                    "mensagem=ASCII(hash_documento), "
                    "assinatura=base64_decode(signature_base64), hash=SHA-256, "
                    "mgf=MGF1-SHA256, salt=32) == True"
                ),
            },
            "pertencimento_ao_acumulador": {
                "descricao": (
                    "Prova matemática de que esta assinatura está incluída "
                    "no conjunto de assinaturas registradas no sistema, sem "
                    "expor as demais assinaturas."
                ),
                "equacao_de_verificacao": "witness^x ≡ acumulador (mod n)",
                "acumulador_hex": state.state_value_hex,
                "modulo_n_hex": state.modulus_n_hex,
                "gerador_hex": state.generator_hex,
                "gerador_contador": state.base_counter,
                "gerador_derivacao": (
                    "Base derivada deterministicamente: g = h² mod N, com "
                    "h = SHA-256('ACCUMULATOR-BASE-V1:' ‖ N ‖ ':' ‖ gerador_contador) "
                    "mod N, exigindo gcd(h, N) = 1 e g ∉ {0, 1}."
                ),
                "x_hex": element.x_value_hex,
                "x_nonce": element.x_nonce,
                "x_derivacao": (
                    "Representante primo derivado de "
                    "SHA-256('H2P-V1:' ‖ hash_evento ‖ ':' ‖ x_nonce), tornado "
                    "ímpar e validado por Miller-Rabin; x_nonce é o contador que "
                    "produziu o primo."
                ),
                "witness_hex": witness.witness_value_hex,
            },
        },
    }


@router.get("/{validation_code}/original", responses=(
    _401 |
    err(403, "Sem permissão",
        "Você não tem permissão para baixar o documento original.") |
    err(404, "Não encontrado", "Assinatura ou arquivo original não encontrado.") |
    err(409, "Integridade violada",
        "O arquivo original armazenado não corresponde ao hash registrado.") |
    _500
))
async def download_original_document(
    validation_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Serve o PDF ORIGINAL (pré-selo) para verificação dos bytes do arquivo.

    Acesso RESTRITO: embora o hash, a assinatura RSA-PSS e a prova de
    pertencimento ao acumulador sejam públicos, o download do documento
    original exige autenticação e autorização, sendo permitido apenas à
    empresa proprietária e aos signatários do documento, pois o arquivo pode
    conter dados pessoais (LGPD).

    O hash registrado e assinado refere-se a este arquivo — o PDF selado tem
    bytes diferentes por construção. Antes de servir, o servidor reconfere o
    SHA-256 do arquivo em disco contra o hash registrado e se recusa a
    entregar um arquivo adulterado como se fosse o original (409).
    """
    document = await signature_service.get_document_by_validation_code(
        db, validation_code
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada.",
        )

    if not await document_service.can_user_access_document(
        db, current_user, document.document_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para baixar o documento original.",
        )

    def _read_file(path: str | None) -> bytes | None:
        if not path:
            return None
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return None
        return file_path.read_bytes()

    file_bytes = await asyncio.to_thread(_read_file, document.file_path)
    if file_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo original do documento não encontrado.",
        )

    actual_hash = hashlib.sha256(file_bytes).hexdigest()
    if actual_hash != document.hash_sha256:
        logger.error(
            "Recusado download do original: hash do arquivo difere do "
            "registrado. validation_code=%s document_id=%s",
            validation_code,
            document.document_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O arquivo original armazenado não corresponde ao hash "
                "registrado no momento do upload (possível adulteração do "
                "armazenamento). O hash registrado permanece a referência "
                "probatória — consulte o portal de validação."
            ),
        )

    filename = document.file_name or "documento-original.pdf"
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}",
            "X-Document-SHA256": actual_hash,
        },
    )


@router.post("/{validation_code}/verify-integrity", responses=(
    err(400, "Arquivo inválido", "Envie um arquivo PDF não vazio.") |
    err(404, "Não encontrado", "Assinatura não encontrada.") |
    err(413, "Arquivo muito grande", "O arquivo enviado excede o limite de 10MB.") |
    _500
))
async def verify_document_integrity(
    validation_code: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica, de forma pública e independente, se uma CÓPIA do documento
    fornecida pelo verificador continua íntegra em relação ao que foi
    assinado sob este código de validação.

    O verificador envia o arquivo (normalmente o PDF SELADO baixado após a
    assinatura); o servidor recalcula o SHA-256 e o compara com dois valores
    de referência registrados no momento da assinatura:

      - ``signed_file_sha256``: hash do PDF SELADO entregue ao usuário — é a
        verificação de integridade PÓS-ASSINATURA (o documento final não foi
        alterado depois de assinado);
      - ``hash_sha256``: hash do PDF ORIGINAL (anterior ao selo) — referência
        probatória do conteúdo assinado.

    A resposta indica contra qual referência o arquivo correspondeu, de modo
    que enviar o selado ou o original produza um resultado correto e
    informativo.
    """
    row = await signature_service.get_document_and_signature_by_validation_code(
        db, validation_code
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada.",
        )
    document, signature = row

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie um arquivo PDF não vazio.",
        )
    if len(file_bytes) > _MAX_VERIFY_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="O arquivo enviado excede o limite de 10MB.",
        )

    computed_hash = await asyncio.to_thread(
        lambda: hashlib.sha256(file_bytes).hexdigest()
    )

    matches_signed = (
        signature.signed_file_sha256 is not None
        and computed_hash == signature.signed_file_sha256
    )
    matches_original = computed_hash == document.hash_sha256
    integro = matches_signed or matches_original

    if matches_signed:
        versao = "selado"
        status_msg = "Documento assinado íntegro"
        mensagem = (
            "O arquivo enviado é o documento SELADO entregue após a "
            "assinatura e não sofreu nenhuma alteração desde então."
        )
    elif matches_original:
        versao = "original"
        status_msg = "Documento original íntegro"
        mensagem = (
            "O arquivo enviado é o documento ORIGINAL (anterior ao selo "
            "visual) e corresponde exatamente ao conteúdo que foi assinado."
        )
    else:
        versao = None
        status_msg = "Documento adulterado ou não corresponde a esta assinatura"
        mensagem = (
            "O arquivo enviado NÃO corresponde nem ao documento selado nem ao "
            "original desta assinatura. Ele pode ter sido alterado após a "
            "assinatura."
        )
        logger.info(
            "Verificação de integridade por upload falhou (hash divergente). "
            "validation_code=%s",
            validation_code,
        )

    return {
        "integro": integro,
        "versao_correspondente": versao,  # "selado" | "original" | None
        "status": status_msg,
        "mensagem": mensagem,
        "codigo_de_validacao": validation_code,
        "algoritmo_de_hash": "SHA-256",
        "hash_do_arquivo_enviado": computed_hash,
        "hash_documento_selado": signature.signed_file_sha256,
        "hash_documento_original": document.hash_sha256,
    }
