"""
state_graph/tickets/dedupe.py

Wraps base.create_failure_ticket with a check: if an open/investigating
ticket already exists for the same (thread_id, node_name, error_message),
reuse it instead of opening a duplicate. Without this, retrying the same
failing node (e.g. a bad role_title, a flaky MCP call) opens one new
ticket per attempt, flooding the tickets panel with copies of the same
underlying problem -- exactly what happened when testing the internship
graph with an unregistered job role.

This does NOT change behavior for stagnation tickets (those already have
their own prefix-based dedupe in stagnation_check.py) -- this is for the
ordinary _ticket_error path every graph's runner uses.
"""

from typing import Optional

from state_graph.base import get_db_connection, create_failure_ticket


def _find_open_ticket(thread_id: str, node_name: str, error_message: str) -> Optional[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM failure_tickets
        WHERE thread_id = ? AND node_name = ? AND error_message = ?
          AND status IN ('open', 'investigating')
        ORDER BY id DESC LIMIT 1
    """, (thread_id, node_name, error_message))
    row = cursor.fetchone()
    conn.close()
    return row["id"] if row else None


def create_ticket_if_not_open(thread_id: str, node_name: str, error_message: str) -> int:
    """
    Same signature/return type as base.create_failure_ticket (returns a
    ticket_id) -- drop-in replacement for runners. Reuses an existing
    open ticket for the identical (thread_id, node_name, error_message)
    instead of creating a duplicate; only opens a new one if the error
    is new or the previous one was already resolved.
    """
    existing_id = _find_open_ticket(thread_id, node_name, error_message)
    if existing_id is not None:
        print(f">>> [Tickets] Reusing existing open ticket #{existing_id} (same failure, not duplicating)")
        return existing_id

    return create_failure_ticket(thread_id, node_name, error_message)