from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import app.models
from app.core.config import settings

from app.api.v1.endpoints import (
    user_controller,
    auth_controller,
    document_controller,
    health,
    otp_controller,
    face_verification,
    document_signer_controller,
    signature_controller,
    accumulator_controller,
    public_signature_controller,
    webhook_controller,
)

app = FastAPI(title="Sistema de Assinatura Eletrônica")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

@app.get("/")
async def root():
    return {"status": "ok"}

app.include_router(user_controller.router)
app.include_router(auth_controller.router)
app.include_router(document_controller.router)
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(otp_controller.router)
app.include_router(face_verification.router)
app.include_router(document_signer_controller.router)
app.include_router(signature_controller.router)
app.include_router(accumulator_controller.router)
app.include_router(public_signature_controller.router)
app.include_router(webhook_controller.router)
