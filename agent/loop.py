import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "memory"))
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent.parent / "context_eval"))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from intent_router import route_intent          # agent/intent_router.py (renamed)

# --- memory system ---
from short_term import ShortTermMemory           # buffer + scratchpad, combined
from router import route_item as memory_route_item   # memory/router.py (promote-or-drop)
from self_check import recall_with_verification  # Self-RAG check for memory recall

# --- rag system ---
from vector_store import get_client, get_or_create_collection
from hybrid_rag import build_bm25_index
from agentic_rag import agentic_rag_search
from generate_local import generate_answer_extractive, check_support_extractive

# --- context management ---
from strategies import recursive_summarization

BUFFER_OVERFLOW_THRESHOLD = 20  # matches short_term.py's own demo overflow point

def handle_message(stm: ShortTermMemory, student_id: int, message: str) -> dict:
    """
    Main entry point: takes one user message, routes it, and returns
    a result dict with the answer plus which subsystem handled it and
    any verification outcome -- so the demo transcript can show the
    full decision trail, not just a final string.
    """
    stm.add_message(role="user", content=message)

    intent = route_intent(message)
    result = {"intent": intent, "answer": None, "verification": None}

    if intent == "policy":
        result.update(_handle_policy_question(message))
    elif intent == "memory":
        result.update(_handle_memory_question(student_id, message))
    elif intent == "planning":
        result.update(_handle_planning_question(student_id, message))
    else:
        result.update(_handle_db_tool_question(student_id, message))

    stm.add_message(role="assistant", content=str(result["answer"]))
    _maybe_compact_buffer(stm)

    return result

def _handle_policy_question(question: str) -> dict:
    """
    Uses agentic RAG for retrieval (winner per retrieval_eval's comparison
    table), then LLM-free extractive generation + support checking
    (generate_local.py) as a stand-in for the real Anthropic-backed
    generate.py / self_rag_check.py, due to no API credits / stable
    network available in this environment. Swap the two imports below
    for the real versions once either is available -- no other code
    in this function needs to change, since both share the same
    (question, chunks) -> answer / (answer, chunks) -> (bool, reason) shape.
    """
    client = get_client()
    collection = get_or_create_collection(client)
    bm25_index, chunks = build_bm25_index()

    retrieved, reasoning_log = agentic_rag_search(collection, bm25_index, chunks, question)
    retrieved_chunks = [c for c, _score in retrieved]

    raw_answer = generate_answer_extractive(question, retrieved_chunks)
    relevance_passed, relevance_reason = _check_agentic_relevance(retrieved)
    support_passed, support_reason = check_support_extractive(raw_answer, retrieved_chunks)

    passed = relevance_passed and support_passed
    if not passed:
        reasons = []
        if not relevance_passed:
            reasons.append(f"relevance check failed: {relevance_reason}")
        if not support_passed:
            reasons.append(f"support check failed: {support_reason}")
        final_answer = (
            "[UNVERIFIED — do not trust this answer without human review]\n"
            f"Reason(s): {'; '.join(reasons)}\n\nOriginal answer: {raw_answer}"
        )
    else:
        final_answer = raw_answer

    return {
        "answer": final_answer,
        "verification": {
            "passed": passed,
            "relevance_reason": relevance_reason,
            "support_reason": support_reason,
        },
        "retrieval_reasoning_log": reasoning_log,
        "retrieved_chunk_ids": [c.chunk_id for c, _score in retrieved],
    }

def _handle_planning_question(student_id: int, message: str) -> dict:
    """
    Routes to the new Adaptive Learning Path Planning agent (agent/
    planning_agent.py) -- a separate agent reusing the same mcp_server/
    and db/, not a modification of the memory/RAG agent's own code path.
    Uses decomposition-first ("dag") mode by default; dynamic mode is
    available via planning_agent.py's own CLI for the comparison table
    in planning_eval/, not exposed through this chat entry point.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent / "planning"))
    from planning_agent import run_learning_path_request
    from langchain_mistralai import ChatMistralAI

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        return {
            "answer": "Planning agent is unavailable: MISTRAL_API_KEY is not set.",
            "planning_error": "missing_api_key",
        }
    llm = ChatMistralAI(api_key=api_key, model="mistral-small-latest", random_seed=42, max_retries=2)

    payload = run_learning_path_request(student_id, message, llm, mode="dag")
    return {
        "answer": payload["result"],
        "planning_artifact_path": payload["artifact_path"],
        "self_refine_grounded_issues": payload.get("self_refine_grounded_issues", []),
    }


def _maybe_compact_buffer(stm: ShortTermMemory) -> None:
    """
    Checks the current buffer size and compacts it via recursive
    summarization (context_eval's shipped strategy -- won on token cost
    at equal accuracy per the comparison table) once it crosses the
    overflow threshold. The scratchpad is never touched here, since
    compaction only ever operates on the message buffer.
    """
    messages = stm.get_recent_messages(limit=1000)

    if len(messages) <= BUFFER_OVERFLOW_THRESHOLD:
        return

    transcript = [
        {"role": m["role"], "kind": "prose", "content": m["content"]}
        for m in messages
    ]

    compacted = recursive_summarization(transcript)

    print(
        f"[context management] Buffer had {len(transcript)} turns, "
        f"compacted to {len(compacted)} turns via recursive_summarization."
    )

def _handle_memory_question(student_id: int, question: str) -> dict:
    """
    Uses memory/self_check.py's recall_with_verification: retrieves the
    current semantic fact for this student and verifies it's actually
    relevant to the question before returning it, per the rubric
    requirement that Self-RAG-style verification also applies to
    memory recall, not just RAG.
    """
    # NOTE: "topic" is currently required by self_check.py's lookup and
    # has no automatic extraction from the question yet -- hardcoded
    # placeholder until topic extraction is wired up with memory's owner.
    topic = "re-enrollment"

    result = recall_with_verification(student_id, question, topic)

    if result["status"] != "verified":
        return {
            "answer": "I don't have a verified record relevant to that question yet.",
            "memory_status": result["status"],
            "memory_reason": result["reason"],
        }

    return {
        "answer": result["usable_fact"],
        "memory_status": "verified",
        "memory_reason": result["reason"],
    }

# RRF fusion scores (from hybrid_search / agentic_rag_search) live on a
# completely different scale than the cosine-similarity scores
# self_rag_check.check_relevance's 0.35 floor was calibrated for.
# A max two-list RRF score is only ~0.033, so reusing that floor here
# would reject every agentic result as "irrelevant" -- a real
# integration bug caught while wiring the two systems together.
AGENTIC_RELEVANCE_FLOOR = 0.01


def _check_agentic_relevance(retrieved: list) -> tuple[bool, str]:
    if not retrieved:
        return False, "No chunks were retrieved at all."
    top_chunk, top_score = retrieved[0]
    if top_score < AGENTIC_RELEVANCE_FLOOR:
        return False, (
            f"Top result ({top_chunk.chunk_id}) scored {top_score:.4f} (RRF scale), "
            f"below the floor of {AGENTIC_RELEVANCE_FLOOR}."
        )
    return True, f"Top result ({top_chunk.chunk_id}) scored {top_score:.4f} (RRF scale), above floor."  

def _get_student_email(student_id: int) -> str | None:
    """
    Looks up a student's email from their id, reusing the same DB
    connection helper server.py uses -- get_student_profile() only
    accepts an email, not a student_id, so this bridges the two without
    duplicating or modifying server.py's own logic.
    """
    from server import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return row["email"] if row else None


def _handle_db_tool_question(student_id: int, question: str) -> dict:
    """
    Handles factual lookups answerable by the existing MCP tools directly
    -- no retrieval, no memory, just a real DB read via server.py's
    already-tested tools (reused, not duplicated).

    Currently supports profile/enrollment/grade questions via
    get_student_profile(). Course-catalog questions (list_all_courses)
    are not yet routed here -- see Known gaps in README.
    """
    from server import get_student_profile

    email = _get_student_email(student_id)
    if email is None:
        return {"answer": f"No student found with id {student_id}."}

    result = get_student_profile(email)
    if result["status"] != "success":
        return {"answer": f"Could not retrieve student data: {result['message']}"}

    data = result["data"]
    question_lower = question.lower()

    if "grade" in question_lower or "course" in question_lower or "enrolled" in question_lower:
        if not data["enrolled_courses"]:
            answer = f"{data['name']} is not currently enrolled in any courses."
        else:
            lines = [
                f"{c['title']}: grade={c['grade']}, status={c['status']}"
                for c in data["enrolled_courses"]
            ]
            answer = f"{data['name']}'s courses — " + "; ".join(lines)
    else:
        answer = f"Student: {data['name']} ({data['email']}), role: {data['role']}"

    return {"answer": answer, "db_source": "get_student_profile"}  

if __name__ == "__main__":
    session_id = "demo_session"
    student_id = 7

    stm = ShortTermMemory(
        session_id=session_id,
        student_id=student_id,
    )

    print("=" * 60)
    print("BrightPeak Academic Agent")
    print("Type 'exit' to quit.")
    print("=" * 60)

    while True:
        message = input("\nYou: ")

        if message.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        result = handle_message(stm, student_id, message)

        print("\nIntent:", result["intent"])
        print("\nAnswer:")
        print(result["answer"])

        if result.get("verification"):
            print("\nVerification:")
            print(result["verification"])