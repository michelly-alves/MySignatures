
import logging
from fastapi import APIRouter, Form, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Códigos de erro Twilio com impacto no fluxo OTP
_DELIVERY_FAILURES = {
    63015: "Número não inscrito no sandbox WhatsApp (opt-in ausente)",
    63016: "Destinatário optou por sair do canal WhatsApp",
    21211: "Número de telefone inválido",
    21608: "Número não verificado na conta Twilio",
}


@router.post("/twilio-status")
async def twilio_status_callback(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    To: str = Form(...),
    From_: str = Form(None, alias="From"),
    ErrorCode: str = Form(None),
    ErrorMessage: str = Form(None),
):

    error_code = int(ErrorCode) if ErrorCode else None

    if MessageStatus in ("failed", "undelivered"):
        friendly = _DELIVERY_FAILURES.get(error_code, ErrorMessage or "Motivo desconhecido")
        logger.error(
            "Falha na entrega de OTP via WhatsApp | "
            "sid=%s | to=%s | status=%s | error_code=%s | detail=%s",
            MessageSid, To, MessageStatus, error_code, friendly,
        )

        if error_code == 63015:
            logger.warning(
                "AÇÃO NECESSÁRIA: o número %s precisa enviar 'join <keyword>' "
                "para %s antes de receber mensagens no sandbox Twilio.",
                To, From_,
            )
    else:
        logger.info(
            "Status WhatsApp | sid=%s | to=%s | status=%s",
            MessageSid, To, MessageStatus,
        )

    return Response(status_code=200)
