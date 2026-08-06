"""
memory/episodic_store.py

Stores raw episodic events (things that happened) in the same
brightpeak.db used by the MCP server. Kept separate from the
messages table: episodic events are meaning-level records
("student asked about X"), not raw chat turns.

Semantic facts (durable, consolidated knowledge) live in their own
table here too, but are only ever written by consolidation.py —
never directly by this module or the router.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "brightpeak.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_episodic_tables():
    """Creates the episodic_events and semantic_facts tables if missing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodic_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            session_id TEXT,
            event_type TEXT NOT NULL,
            event_summary TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semantic_facts (
            fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            fact_text TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            is_current BOOLEAN DEFAULT 1,
            valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_until TIMESTAMP,
            superseded_by INTEGER
        )
    """)

    conn.commit()
    conn.close()


# Ensure tables exist as soon as this module loads (same pattern as server.py)
init_episodic_tables()

def log_event(student_id: int, session_id: str, event_type: str, event_summary: str) -> dict:
    """
    Records a single episodic event. This is called by router.py when it
    decides an aging short-term item is worth promoting — never called
    directly for semantic facts.
    """
    if not event_type or not event_type.strip():
        return {"status": "error", "message": "event_type is required."}

    if not event_summary or not event_summary.strip():
        return {"status": "error", "message": "event_summary is required."}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO episodic_events (student_id, session_id, event_type, event_summary)
            VALUES (?, ?, ?, ?)
            """,
            (student_id, session_id, event_type, event_summary),
        )
        conn.commit()
        return {
            "status": "success",
            "event_id": cursor.lastrowid,
            "message": "Event logged.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()


def get_events_for_student(student_id: int, event_type: str = None) -> list:
    """
    Returns all episodic events for a student, optionally filtered by type.
    consolidation.py uses this to find repeated events worth turning into
    a semantic fact.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if event_type:
        cursor.execute(
            """
            SELECT * FROM episodic_events
            WHERE student_id = ? AND event_type = ?
            ORDER BY created_at ASC
            """,
            (student_id, event_type),
        )
    else:
        cursor.execute(
            "SELECT * FROM episodic_events WHERE student_id = ? ORDER BY created_at ASC",
            (student_id,),
        )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_events_by_type(student_id: int) -> dict:
    """
    Returns a count of events grouped by event_type for a student.
    Useful for consolidation.py to spot 'this happened 3+ times' patterns.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT event_type, COUNT(*) as count
        FROM episodic_events
        WHERE student_id = ?
        GROUP BY event_type
        """,
        (student_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return {row["event_type"]: row["count"] for row in rows}

if __name__ == "__main__":
    pass 