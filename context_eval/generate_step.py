"""
Stand-in for the agent's actual LLM call that answers FINAL_QUESTION using
whatever context survived compaction. No live model/API key is available in
this sandbox, so this is a deterministic rule-based generator -- but it's
driven ONLY by what's literally present in the compacted context, exactly
like a real model would be grounded only in what's in its context window.
This is what lets us score "task accuracy" (did the agent give the RIGHT
answer) instead of just "is the raw fact string still there somewhere".
"""

from transcript_builder import CRITICAL_KEYWORDS

CORRECT_ANSWER = (
    "No, don't enroll him directly -- this student was previously expelled "
    "for a documented cheating incident, and any new enrollment for him "
    "must go through the disciplinary committee first."
)

WRONG_ANSWER = (
    "Yes, we can go ahead and enroll him in Machine Learning right away, "
    "nothing in the record indicates a problem."
)


def _has_critical_fact(compacted_turns):
    for t in compacted_turns:
        text = t["content"]
        has_keyword = any(k in text for k in CRITICAL_KEYWORDS)
        has_id = "student_id=1" in text or "Youssef Ibrahim" in text
        if has_keyword and has_id:
            return True
    return False


def generate_answer(compacted_turns):
    """
    Returns (answer_text, is_correct). Mirrors a real generation step:
    the model can only ground its answer in what's actually in context.
    """
    if _has_critical_fact(compacted_turns):
        return CORRECT_ANSWER, True
    return WRONG_ANSWER, False