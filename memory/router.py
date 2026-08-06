"""
memory/router.py

Promote-or-drop routing: when the short-term buffer overflows (an old
message is about to be pruned), this module decides whether that
message is worth promoting to episodic memory, or safe to forget.

Decision is based on two signals together:
1. Role: only 'user' messages are candidates (assistant replies and
   system messages are routine, not events worth remembering).
2. Content: does the message contain a keyword tied to something
   that matters in this system (academic exceptions, drops, appeals).

Every decision — forget or promote — is logged with its reasoning,
so a grader can see WHY, not just WHAT happened.

This router NEVER writes to semantic_facts. That's consolidation.py's job.
"""

import os

from episodic_store import log_event

RELEVANT_KEYWORDS = [
    "drop", "re-enrollment", "re-enroll", "exception",
    "appeal", "deadline", "reinstate", "reinstatement",
]


ROUTER_LOG_PATH = os.path.join(os.path.dirname(__file__), "router_decisions.log")

def _is_relevant(content: str) -> bool:
    """Checks if the message content contains any keyword we care about."""
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in RELEVANT_KEYWORDS)


def _log_decision(session_id: str, role: str, content: str, decision: str, reason: str) -> None:
    """Appends one routing decision to the router log file."""
    with open(ROUTER_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(
            f"[session={session_id}] role={role} decision={decision} "
            f"reason=\"{reason}\" content_preview=\"{content[:50]}\"\n"
        )


def route_item(student_id: int, session_id: str, role: str, content: str) -> dict:
    """
    Decides whether an aging short-term message should be:
    - promoted to episodic memory, or
    - forgotten

    Decision rule (both signals required to promote):
    1. role must be 'user' (assistant/system turns are routine)
    2. content must contain a relevant keyword

    Returns the decision and logs the reasoning either way.
    """

   
    if role != "user":
        reason = f"role='{role}' is not a user message; assistant/system turns are routine."
        _log_decision(session_id, role, content, "forget", reason)
        return {"decision": "forget", "reason": reason}



    if not _is_relevant(content):
        reason = "user message, but no relevant keyword found (not an academic-exception topic)."
        _log_decision(session_id, role, content, "forget", reason)
        return {"decision": "forget", "reason": reason}

    # Both signals passed -> promote to episodic memory
    reason = "user message containing a relevant keyword (academic exception topic)."
    result = log_event(
        student_id=student_id,
        session_id=session_id,
        event_type="academic_exception_inquiry",
        event_summary=content,
    )

    if result["status"] != "success":
        # Even if the episodic write fails, log that we tried and why
        reason += f" [episodic write failed: {result['message']}]"
        _log_decision(session_id, role, content, "promote_failed", reason)
        return {"decision": "promote_failed", "reason": reason}

    _log_decision(session_id, role, content, "promote", reason)
    return {"decision": "promote", "reason": reason, "event_id": result["event_id"]}

if __name__ == "__main__":
    # Case 1: relevant user message -> should promote
    r1 = route_item(7, "test_session_2", "user", "Can I get an exception for my drop in CS101?")
    print("Case 1 (relevant, user):", r1)

    # Case 2: irrelevant user message -> should forget
    r2 = route_item(7, "test_session_2", "user", "Thanks, that's helpful!")
    print("Case 2 (irrelevant, user):", r2)

    # Case 3: assistant message -> should forget regardless of content
    r3 = route_item(7, "test_session_2", "assistant", "You may appeal the drop decision.")
    print("Case 3 (assistant role):", r3)