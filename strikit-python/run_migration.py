import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def run_migration():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        try:
            await conn.execute(text('ALTER TABLE "BotOwner" ADD COLUMN "weekendPricePerHourPaise" INTEGER;'))
            print("Migration successful")
        except Exception as e:
            print(f"Migration error: {e}")
    await engine.dispose()

asyncio.run(run_migration())
