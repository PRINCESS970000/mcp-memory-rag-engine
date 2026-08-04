import sqlite3
import os

def init_database():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    db_path = os.path.join(current_dir, "brightpeak.db")
    schema_path = os.path.join(current_dir, "schema.sql")
    seed_path = os.path.join(current_dir, "seed.sql")

    if os.path.exists(db_path):
        os.remove(db_path)
        print("[DB] Removed old database instance.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    with open(schema_path, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())
    print("[DB] Schema created successfully.")

    with open(seed_path, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())
    print("[DB] Seed data inserted successfully.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()