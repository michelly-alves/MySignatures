from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

engine = None
AsyncSessionLocal = None

def get_async_url(url: str) -> str:
    """Garante que a URL use o driver assíncrono asyncpg."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

if DATABASE_URL:
    try:
        async_url = get_async_url(DATABASE_URL)
        
        engine = create_async_engine(
            async_url,
            echo=False,
            future=True
        )

        AsyncSessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    except Exception:
        pass

async def get_db():
    """Dependency para o FastAPI."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL não configurada ou erro ao inicializar motor assíncrono. "
            "Verifique seu arquivo .env e se o banco de dados está online."
        )
    async with AsyncSessionLocal() as session:
        yield session
