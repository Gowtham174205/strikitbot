"""
SQLAlchemy async database engine and session management.
Uses asyncpg driver for PostgreSQL with connection pooling.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# Convert DATABASE_URL to async format if needed
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Remove pgbouncer params for direct connection
db_url = db_url.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")

# SQLite compatibility for testing
connect_args = {}
extra_args = {}
if db_url.startswith("sqlite"):
    from sqlalchemy.pool import StaticPool
    extra_args["poolclass"] = StaticPool
    connect_args["check_same_thread"] = False
else:
    extra_args["pool_size"] = 10
    extra_args["max_overflow"] = 20
    connect_args["statement_cache_size"] = 0
    connect_args["prepared_statement_cache_size"] = 0
    from uuid import uuid4
    connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4().hex}__"

engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
    **extra_args
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables on startup (dev only). Use Alembic in production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            from sqlalchemy import text
            await conn.execute(text('ALTER TABLE "BotOwner" ADD COLUMN IF NOT EXISTS address VARCHAR(500)'))
            await conn.execute(text('ALTER TABLE "BotOwner" ADD COLUMN IF NOT EXISTS "searchKeywords" VARCHAR(1000)'))
        except Exception:
            pass


async def close_db():
    """Dispose engine connections on shutdown."""
    await engine.dispose()
