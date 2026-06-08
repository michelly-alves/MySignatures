import logging
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import signature_service
from app.api.v1.responses import err, _500

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/signatures", tags=["Public Signatures"])

_BRT = timezone(timedelta(hours=-3))

_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


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

        "documento": {
            "hash_sha256": document.hash_sha256,
            "algoritmo_de_hash": "SHA-256",
            "observacao": (
                "Hash do arquivo PDF original. Para confirmar que o documento "
                "não foi alterado, calcule o SHA-256 do arquivo e compare com "
                "o hash acima."
            ),
        },

        "evento_de_assinatura": {
            "descricao": (
                "Cada evento de assinatura é mapeado para um hash composto "
                "que inclui o documento, identificadores internos da operação "
                "e o momento da assinatura. Esse hash é o que é efetivamente "
                "registrado no acumulador. Os identificadores internos não são "
                "expostos publicamente — a verificação criptográfica de "
                "pertencimento usa diretamente o valor `x` (campo `x_hex` na "
                "prova técnica), sem depender da reprodução do hash composto."
            ),
            "hash_composto_sha256": element.hash_hex,
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
                "algoritmo": "RSA-PSS com SHA-256 e salt de 32 bytes",
                "signature_base64": signature.signature_data,
                "public_key_pem": safe_public_key,
                "equacao_de_verificacao": (
                    "RSA-PSS.verify(public_key_pem, sha256(documento), "
                    "signature_base64) == True"
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
                "x_hex": element.x_value_hex,
                "x_nonce": element.x_nonce,
                "witness_hex": witness.witness_value_hex,
            },
        },
    }
