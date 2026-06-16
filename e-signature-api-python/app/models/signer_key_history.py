from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.db.base import Base


class SignerKeyHistory(Base):
    """
    Histórico de chaves públicas revogadas de um signatário.

    Quando o signatário rotaciona a chave (perda do .ekey ou da senha), a
    chave anterior é movida para esta tabela com data e motivo da revogação.
    Preserva a auditabilidade: assinaturas antigas continuam verificáveis
    contra a chave que era a âncora no momento da assinatura (cada assinatura
    guarda sua própria public_key_pem em digital_signature).
    """

    __tablename__ = "signer_key_history"

    history_id = Column(Integer, primary_key=True)
    signer_id = Column(
        Integer, ForeignKey("signer.signer_id"), nullable=False, index=True
    )
    public_key = Column(String, nullable=False)
    revoked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String, nullable=True)
    revoked_by = Column(Integer, nullable=True)  # user_id que executou a rotação
