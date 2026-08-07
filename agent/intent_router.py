"""
Top-level intent routing for the agent loop.
"""

POLICY_KEYWORDS = [
    "policy",
    "deadline",
    "allowed",
    "eligib",
    "appeal",
    "reissue",
    "grounds",
    "section",
    "procedure",
    "process",
]

MEMORY_KEYWORDS = [
    "remember",
    "memory",
    "last time",
    "before",
    "previously",
    "already told",
    "we discussed",
    "earlier",
    "again",
    "my request",
    "my application",
    "my case",
    "my history",
    "did i",
    "have i",
]

DB_KEYWORDS = [
    "grade",
    "grades",
    "course",
    "courses",
    "student",
    "profile",
    "email",
    "status",
    "enrolled",
    "gpa",
]

def route_intent(message: str) -> str:
    text = message.lower()

    # Memory questions first
    if any(k in text for k in MEMORY_KEYWORDS):
        return "memory"

    # Database questions
    if any(k in text for k in DB_KEYWORDS):
        return "db_tool"

    # Policy questions
    if any(k in text for k in POLICY_KEYWORDS):
        return "policy"

    # Re-enrollment:
    # if user asks to REMEMBER -> memory
    # otherwise -> policy
    if "re-enrollment" in text or "re enrollment" in text or "re-enroll" in text:
        if "remember" in text or "previous" in text or "before" in text:
            return "memory"
        return "policy"

    return "db_tool"