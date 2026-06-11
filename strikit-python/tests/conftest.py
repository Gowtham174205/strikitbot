"""Pytest fixtures for STRIKIT tests. Configures SQLite in-memory DB and httpx client."""
import pytest
import os
import asyncio
from httpx import AsyncClient

# Set environment variables for testing
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ADMIN_API_KEY"] = "test-admin-key-12345"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "STRIKIT_TOKEN"
os.environ["DEVELOPER_NUMBERS"] = "919876543210"
os.environ["WHATSAPP_APP_SECRET"] = ""
os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""
os.environ["RAZORPAY_WEBHOOK_SECRET"] = ""
os.environ["WHATSAPP_ACCESS_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["RAZORPAY_KEY_ID"] = ""
os.environ["RAZORPAY_KEY_SECRET"] = ""
os.environ["RAZORPAYX_ACCOUNT_NUMBER"] = ""
os.environ["NODE_ENV"] = "development"

from app.main import app
from app.database import Base, engine, async_session_factory, get_db

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def setup_db():
    """Initialize test database tables before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session():
    """Yields an independent database session for setup/asserts in tests."""
    async with async_session_factory() as session:
        yield session

@pytest.fixture
async def client(setup_db, db_session):
    """Async client with overridden database dependency."""
    async def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
