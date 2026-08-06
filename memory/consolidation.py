"""
memory/consolidation.py

Periodic consolidation pass over episodic memory. Turns repeated or
decision-bearing episodic events into durable semantic facts.

Runs SEPARATELY from the router (router.py never writes here directly).
Handles the real problem semantic facts hit in production:
- updates when a fact changes
- versioning so an old fact isn't silently lost
- conflict resolution when two episodes imply contradictory facts

Conflict resolution rule used here: the most recent decision wins,
but the old fact is never deleted — it's marked superseded, with a
version number and a link to what replaced it.
"""

import os
import sqlite3

from episodic_store import get_db_connection, get_events_for_student

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "brightpeak.db")

DECISION_KEYWORDS = {
    "APPROVED": "approved",
    "DENIED": "denied",
}

def _extract_decision(event_summary: str) -> str:
    """
    Looks at an event summary and returns 'APPROVED', 'DENIED', or
    None if no known decision keyword is found.
    """
    summary_lower = event_summary.lower()
    for label, keyword in DECISION_KEYWORDS.items():
        if keyword in summary_lower:
            return label
    return None


def _get_current_fact(student_id: int, topic: str) -> dict:
    """
    Returns the current (is_current=1) semantic fact for a student on a
    given topic, or None if none exists yet.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM semantic_facts
        WHERE student_id = ? AND fact_text LIKE ? AND is_current = 1
        """,
        (student_id, f"%{topic}%"),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def consolidate_student(student_id: int, event_type: str, topic: str) -> dict:
    """
    The main consolidation pass for one student + topic.

    1. Pulls all episodic events of `event_type` for this student.
    2. Finds the LATEST event that carries a decision (APPROVED/DENIED).
    3. Compares it to the current semantic fact (if any) on this topic.
    4. If they conflict, resolves it: the new decision becomes current,
       the old fact is versioned and marked superseded (never deleted).
    5. If there's no existing fact yet, just creates the first one.

    This is meant to be called periodically (e.g. a scheduled job),
    NOT at write time — router.py never calls this directly.
    """
    events = get_events_for_student(student_id, event_type=event_type)

    if not events:
        return {"status": "no_events", "message": "No episodic events found for this student/type."}

    # Find the most recent event that actually carries a decision,
    # scanning from the end since events come back oldest -> newest.
    latest_decision = None
    latest_event = None
    for event in reversed(events):
        decision = _extract_decision(event["event_summary"])
        if decision:
            latest_decision = decision
            latest_event = event
            break

    if not latest_decision:
        return {"status": "no_decision_found", "message": "No decision keyword found in any event."}

    new_fact_text = f"{topic}: {latest_decision} (as of event {latest_event['event_id']}, {latest_event['created_at']})"

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        current_fact = _get_current_fact(student_id, topic)

        if current_fact is None:
            # No existing fact — this is the first time we consolidate this topic.
            cursor.execute(
                """
                INSERT INTO semantic_facts (student_id, fact_text, version, is_current)
                VALUES (?, ?, 1, 1)
                """,
                (student_id, new_fact_text),
            )
            conn.commit()
            return {
                "status": "created",
                "fact_id": cursor.lastrowid,
                "fact_text": new_fact_text,
            }

        # A current fact already exists — check for conflict.
        old_decision = "APPROVED" if "APPROVED" in current_fact["fact_text"] else "DENIED"

        if old_decision == latest_decision:
            # Same conclusion, nothing to resolve — no change needed.
            return {
                "status": "unchanged",
                "fact_id": current_fact["fact_id"],
                "fact_text": current_fact["fact_text"],
            }

        # CONFLICT: old fact says one thing, latest episodic evidence says another.
        # Resolution rule: most recent decision wins. Old fact is superseded,
        # not deleted — full version history is preserved.
        new_version = current_fact["version"] + 1

        cursor.execute(
            """
            INSERT INTO semantic_facts (student_id, fact_text, version, is_current)
            VALUES (?, ?, ?, 1)
            """,
            (student_id, new_fact_text, new_version),
        )
        new_fact_id = cursor.lastrowid

        cursor.execute(
            """
            UPDATE semantic_facts
            SET is_current = 0, valid_until = CURRENT_TIMESTAMP, superseded_by = ?
            WHERE fact_id = ?
            """,
            (new_fact_id, current_fact["fact_id"]),
        )

        conn.commit()

        return {
            "status": "conflict_resolved",
            "old_fact": current_fact["fact_text"],
            "new_fact": new_fact_text,
            "new_fact_id": new_fact_id,
            "superseded_fact_id": current_fact["fact_id"],
        }

    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()



if __name__ == "__main__":
    result = consolidate_student(
        student_id=7,
        event_type="re_enrollment_decision",
        topic="CS101 re-enrollment"
    )
    print("Consolidation result:", result)
