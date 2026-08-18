"""
Top-level intent routing for the agent loop.

Priority order matters here: MEMORY > POLICY > DB_TOOL.

POLICY is checked before DB_TOOL specifically because DB_KEYWORDS contains
generic words like "grade" and "course" that also show up naturally inside
policy questions (e.g. "grade appeal", "course withdrawal deadline"). If
DB_TOOL were checked first, every policy question that happens to mention
a DB-flavored word would be misrouted to a plain data lookup instead of
retrieval -- which is exactly what happened before this fix: "What are
the valid grounds for filing a grade appeal?" matched DB_KEYWORDS' "grade"
and was routed to db_tool before POLICY_KEYWORDS' "appeal"/"grounds" ever
got checked.
"""

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

PLANNING_KEYWORDS = [
    "learning path",
    "career path",
    "plan my courses",
    "plan a path",
    "help me plan",
    "roadmap",
    "study plan",
    "course plan",
    "become a data",
    "become a software",
    "become an ml",
    "path to become",
    "plan for me",
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

    # Memory questions first -- referring to something discussed earlier
    # always takes priority, regardless of what topic it's about.
    if any(k in text for k in MEMORY_KEYWORDS):
        return "memory"

    # Policy questions next -- checked BEFORE the generic DB keywords,
    # since policy questions often contain a DB-flavored word (see
    # docstring above) but DB questions rarely contain a policy word.
    if any(k in text for k in POLICY_KEYWORDS):
        return "policy"

    # Learning-path planning requests next -- checked before the generic DB
    # keywords for the same reason as POLICY above: "plan my courses to
    # become a Data Analyst" contains "course", a DB_KEYWORDS word, and
    # would be misrouted to a plain profile lookup if DB_TOOL were checked
    # first instead of recognizing this as a planning request.
    if any(k in text for k in PLANNING_KEYWORDS):
        return "planning"

    # Database lookups -- factual questions about a specific student's
    # current data.
    if any(k in text for k in DB_KEYWORDS):
        return "db_tool"

    # Re-enrollment questions without any of the above keywords:
    # "remember"/"previous"/"before" would already have been caught by
    # MEMORY_KEYWORDS above, so reaching here means it's asking about the
    # re-enrollment rule itself.
    if "re-enrollment" in text or "re enrollment" in text or "re-enroll" in text:
        return "policy"

    return "db_tool"