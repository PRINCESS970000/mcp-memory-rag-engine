"""
memory/self_check.py

Self-RAG-style verification for MEMORY recall (episodic/semantic),
per the assignment requirement that this check applies to both RAG
answers and to memories recalled from the episodic/semantic store.

Before a semantic fact is handed to the agent as an answer, this module
checks whether the recalled fact is actually relevant to the question
being asked — instead of trusting whatever the topic-matching query
handed back.
"""

from episodic_store import get_db_connection
import string

def get_current_fact_for_topic(student_id: int, topic: str) -> dict:
    """
    Retrieves the current semantic fact for a student on a given topic.
    This is the 'retrieval' step — the check below verifies it before use.
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

import string


def _clean_words(text: str) -> set:
    """Lowercases, strips punctuation, and splits into words."""
    text_lower = text.lower()
    # Remove punctuation like ?, :, (, ), ., ,
    translator = str.maketrans("", "", string.punctuation)
    text_clean = text_lower.translate(translator)
    return set(text_clean.split())


def check_relevance(question: str, fact: dict) -> dict:
    """
    Self-RAG-style check: is this recalled fact actually relevant to
    the question being asked?

    Uses substring matching (not exact word equality) so that
    're-enroll' in the question still matches 're-enrollment' in the
    fact — real language varies in word form even when the topic
    is the same.
    """
    if fact is None:
        return {"relevant": False, "reason": "No fact was retrieved to check."}

    question_words = _clean_words(question)
    fact_words = _clean_words(fact["fact_text"])

    meaningful_overlap = set()
    for qw in question_words:
        if len(qw) <= 3:
            continue
        for fw in fact_words:
            if len(fw) <= 3:
                continue
            # Substring match catches 're-enroll' vs 're-enrollment',
            # 'cs101' vs 'cs101', etc.
            if qw in fw or fw in qw:
                meaningful_overlap.add(qw)

    if not meaningful_overlap:
        return {
            "relevant": False,
            "reason": f"No meaningful keyword overlap between question and fact_text='{fact['fact_text']}'.",
        }

    return {
        "relevant": True,
        "reason": f"Shared relevant terms: {meaningful_overlap}",
        "matched_terms": list(meaningful_overlap),
    }

def recall_with_verification(student_id: int, question: str, topic: str) -> dict:
    """
    Full Self-RAG-style flow: retrieve the current fact, then verify
    it's actually relevant before returning it as something the agent
    can use. If verification fails, the agent gets nothing back rather
    than a possibly-wrong fact.
    """
    fact = get_current_fact_for_topic(student_id, topic)
    check = check_relevance(question, fact)

    if not check["relevant"]:
        return {
            "status": "rejected",
            "reason": check["reason"],
            "usable_fact": None,
        }

    return {
        "status": "verified",
        "reason": check["reason"],
        "usable_fact": fact["fact_text"],
    }

if __name__ == "__main__":
    # Case 1: relevant question -> should verify and return the fact
    r1 = recall_with_verification(
        student_id=7,
        question="Can Kareem re-enroll in CS101?",
        topic="CS101 re-enrollment",
    )
    print("Case 1 (relevant question):", r1)

    # Case 2: unrelated question -> should reject even if a fact exists
    r2 = recall_with_verification(
        student_id=7,
        question="What is Kareem's grade in Database Management Systems?",
        topic="CS101 re-enrollment",
    )
    print("Case 2 (unrelated question):", r2)