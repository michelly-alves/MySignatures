import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings


def _send_email(to_email: str, subject: str, body: str):
    remetente_email = settings.EMAIL_USER
    senha_app = settings.EMAIL_PASSWORD
    smtp_server = settings.SMTP_SERVER
    smtp_port_ssl = settings.SMTP_PORT

    if not remetente_email or not senha_app or not smtp_server:
        raise RuntimeError("Configurações de e-mail não configuradas")

    msg = MIMEMultipart()
    msg['From'] = remetente_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port_ssl, context=context) as server:
            server.login(remetente_email, senha_app)
            server.send_message(msg)
        print(f"E-mail enviado com sucesso para {to_email}!")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        raise


def send_set_password_email(to_email: str, full_name: str, reset_link: str):
    subject = "Defina sua senha"

    body = (
        f"Olá {full_name},\n\n"
        "Uma conta foi criada para você.\n"
        "Para definir sua senha, clique no link abaixo:\n\n"
        f"{reset_link}\n\n"
        "O link expira em 24 horas.\n\n"
        "Atenciosamente,\nEquipe"
    )

    _send_email(to_email, subject, body)


def send_forgot_password_email(to_email: str, reset_link: str):
    subject = "Redefinição de senha"

    body = (
        "Olá,\n\n"
        "Recebemos uma solicitação para redefinir a senha da sua conta.\n"
        "Clique no link abaixo para criar uma nova senha:\n\n"
        f"{reset_link}\n\n"
        "O link expira em 1 hora.\n\n"
        "Se você não solicitou essa redefinição, ignore este e-mail."
        " Sua senha permanece a mesma.\n\n"
        "Atenciosamente,\nEquipe E-Signature"
    )

    _send_email(to_email, subject, body)


def send_pending_document_email(
    to_email: str,
    full_name: str,
    document_name: str,
    documents_link: str,
):
    subject = "Documento aguardando assinatura"

    body = (
        f"Olá {full_name},\n\n"
        "Há um novo documento aguardando sua assinatura na plataforma.\n\n"
        f"Documento: {document_name}\n\n"
        "Acesse sua conta pelo link abaixo para visualizar e assinar:\n\n"
        f"{documents_link}\n\n"
        "Atenciosamente,\nEquipe"
    )

    _send_email(to_email, subject, body)
