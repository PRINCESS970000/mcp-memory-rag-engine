import json
import sqlite3
from typing import Any, Dict, Optional

DB_PATH = "db/brightpeak.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_checkpointing_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT,
            node_name TEXT,
            state_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (thread_id, node_name)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hitl_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            details_json TEXT,
            status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failure_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            node_name TEXT NOT NULL,
            error_message TEXT NOT NULL,
            status TEXT DEFAULT 'open', -- 'open', 'investigating', 'resolved'
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)
    
    conn.commit()
    conn.close()

def save_checkpoint(thread_id: str, node_name: str, state: Dict[str, Any]):
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO checkpoints (thread_id, node_name, state_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (thread_id, node_name, json.dumps(state)))
    conn.commit()
    conn.close()

def load_latest_checkpoint(thread_id: str) -> Optional[Dict[str, Any]]:
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT state_json FROM checkpoints 
        WHERE thread_id = ? 
        ORDER BY updated_at DESC LIMIT 1
    """, (thread_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["state_json"])
    return None

def create_hitl_task(thread_id: str, reason: str, details: Dict[str, Any]) -> int:
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hitl_tasks (thread_id, reason, details_json)
        VALUES (?, ?, ?)
    """, (thread_id, reason, json.dumps(details)))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def create_failure_ticket(thread_id: str, node_name: str, error_msg: str) -> int:
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO failure_tickets (thread_id, node_name, error_message)
        VALUES (?, ?, ?)
    """, (thread_id, node_name, error_msg))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id