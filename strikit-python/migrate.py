import asyncio
from app.database import engine
from sqlalchemy import text

async def m():
    try:
        async with engine.begin() as c:
            await c.execute(text('ALTER TABLE "BotBooking" ADD COLUMN IF NOT EXISTS "sport" VARCHAR;'))
            print("Migration successful: sport column verified.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(m())
