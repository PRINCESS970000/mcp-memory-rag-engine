"""
Top-level intent routing for the agent loop.

Decides which subsystem should handle an incoming user message:
  - "db_tool"  -> a factual lookup answerable by an existing MCP tool
                  (student status, grades, enrollment records)
  - "policy"   -> a rules/policy question answerable by the RAG corpus
                  (deadlines, eligibility criteria, procedures)
  - "memory"   -> a question referring to something discussed earlier
                  in this student's history ("what did we decide last time")

This is deliberately simple keyword routing, not another LLM call --
keeping routing cheap and fast matters more than perfect accuracy here,
since a wrong route just means a slightly less direct answer, not a
wrong one (RAG and DB tools both stay grounded either way).
"""

POLICY_KEYWORDS = [
    "policy", "deadline", "allowed", "eligib", "appeal", "reissue",
    "re-enroll", "reenroll", "grounds", "section", "procedure", "process",
]

MEMORY_KEYWORDS = [
    "last time", "before", "previously", "already told", "we discussed",
    "earlier", "again",
]


def route_intent(message: str) -> str:
    text = message.lower()

    if any(k in text for k in MEMORY_KEYWORDS):
        return "memory"
    if any(k in text for k in POLICY_KEYWORDS):
        return "policy"
    return "db_tool"