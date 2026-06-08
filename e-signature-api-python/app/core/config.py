from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    ACCUMULATOR_HMAC_SECRET: str | None = None

    FRONTEND_BASE_URL: str = "http://localhost:53398"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    BACKEND_CORS_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:8080,"
        "http://localhost:55173,"
        "http://127.0.0.1:3000,"
        "http://localhost:53398"
    )

    EMAIL_USER: str | None = None
    EMAIL_PASSWORD: str | None = None
    SMTP_SERVER: str | None = None
    SMTP_PORT: int = 465

    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    TWILIO_STATUS_CALLBACK_URL: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.BACKEND_CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
