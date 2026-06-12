import asyncio
from app.database import engine
from sqlalchemy import inspect

async def main():
    async with engine.connect() as conn:
        insp = await conn.run_sync(inspect)
        tables = ['BotOwner', 'BotBooking', 'BotSession', 'BotTurfSlot', 'BotJoinRequest']
        for table in tables:
            columns = [c['name'] for c in insp.get_columns(table)]
            print(f"TABLE {table}: {columns}")

if __name__ == "__main__":
    asyncio.run(main())
