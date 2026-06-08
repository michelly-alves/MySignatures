import logging
import re
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def normalize_br_phone(number: str) -> str:

    cleaned = re.sub(r"[^\d+]", "", number)

    if cleaned.startswith("+"):
        normalized = cleaned
    else:
        digits = cleaned.lstrip("0")
        if digits.startswith("55") and len(digits) in (12, 13):
            normalized = f"+{digits}"
        elif len(digits) in (10, 11):
            normalized = f"+55{digits}"
        else:
            normalized = f"+{digits}"

    if normalized.startswith("+55") and len(normalized) == 14:
        ddd = normalized[3:5]   
        ninth = normalized[5]  
        rest = normalized[6:]   
        if ninth == "9":
            normalized = f"+55{ddd}{rest}"

    return normalized

# Códigos de erro Twilio conhecidos e suas mensagens amigáveis
_TWILIO_ERROR_MESSAGES: dict[int, str] = {
    63015: (
        "O número de destino não está inscrito no canal WhatsApp. "
        "Em ambiente de testes, o destinatário precisa enviar 'join <keyword>' "
        "para o número do sandbox Twilio antes de receber mensagens."
    ),
    63016: "O número de destino optou por sair do canal WhatsApp.",
    21608: "O número de telefone não é válido ou não está verificado na conta Twilio.",
    21211: "Número de telefone de destino inválido.",
}


async def send_otp_via_whatsapp(to_number: str, otp_code: str) -> str:
    """
    Envia o código OTP via WhatsApp usando a API da Twilio.

    Retorna o SID da mensagem para rastreamento posterior via webhook.

    Raises:
        RuntimeError: para falhas síncronas (credenciais inválidas, rede, etc.).
        Falhas assíncronas (ex.: número não inscrito no sandbox) são detectadas
        via webhook — veja POST /webhooks/twilio-status.
    """
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN

    if not account_sid or not auth_token:
        raise RuntimeError("Credenciais Twilio não configuradas")

    from_number = settings.TWILIO_WHATSAPP_FROM
    normalized = normalize_br_phone(to_number)
    to_formatted = f"whatsapp:{normalized}"
    if normalized != to_number:
        logger.info("Número normalizado: %s → %s", to_number, normalized)
    status_callback = settings.TWILIO_STATUS_CALLBACK_URL

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    data: dict[str, str] = {
        "To": to_formatted,
        "From": from_number,
        "Body": f"Seu código de verificação e-Signature é: *{otp_code}*\n\nVálido por 5 minutos. Não compartilhe este código.",
    }

    if status_callback:
        data["StatusCallback"] = status_callback
        logger.debug("StatusCallback configurado: %s", status_callback)
    else:
        logger.warning(
            "TWILIO_STATUS_CALLBACK_URL não configurado — falhas de entrega "
            "assíncronas (ex.: error 63015) não serão detectadas."
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                data=data,
                auth=(account_sid, auth_token),
            )
    except httpx.TimeoutException:
        raise RuntimeError("Timeout ao conectar com o serviço Twilio")
    except httpx.RequestError as e:
        raise RuntimeError(f"Erro de conexão com o serviço Twilio: {str(e)}")

    if response.status_code == 401:
        raise RuntimeError("Credenciais Twilio inválidas")

    if response.status_code >= 400:
        body = response.json()
        error_code = body.get("code")
        friendly = _TWILIO_ERROR_MESSAGES.get(error_code)
        detail = friendly or body.get("message", response.text[:200])
        raise RuntimeError(f"Erro Twilio [{error_code}]: {detail}")

    if response.status_code >= 500:
        raise RuntimeError("Serviço Twilio indisponível no momento")

    body = response.json()
    message_sid = body.get("sid", "")
    initial_status = body.get("status", "unknown")

    logger.info(
        "OTP enfileirado | to=%s | sid=%s | status=%s",
        to_formatted, message_sid, initial_status,
    )

    return message_sid
