import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strikit.db")

try:
    conn = sqlite3.connect(db_path)
    conn.execute('ALTER TABLE BotOwner ADD COLUMN weekendPricePerHourPaise INTEGER;')
    conn.commit()
    print("Migration successful: added weekendPricePerHourPaise")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("Column already exists. Migration skipped.")
    else:
        print(f"Error during migration: {e}")
finally:
    conn.close()
