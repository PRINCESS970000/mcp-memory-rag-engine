"""
Option B: answer_with_grounding_check

Adds one guardrail on top of the existing search_knowledge_base tool:
before returning an answer, check it's actually backed by the retrieved
chunks, and retry the search exactly ONCE if it isn't.

STATUS: the three TODOs from the original starter version are resolved
below -- RealLLM wraps rag/generate.py's real Anthropic client, and
real_search_knowledge_base wraps rag/agentic_rag.py's real retrieval
(the winning architecture per retrieval_eval's comparison table).

NOTE: this module still isn't the live path for policy questions in
agent/loop.py, because it depends on the Anthropic API (no credits in
this environment -- see generate_local.py). The retry-once PATTERN
demonstrated here is wired into the actual live pipeline in
agent/loop.py's _handle_policy_question, using the offline extractive
components instead. Once API credits are available, call
answer_with_grounding_check(query, real_search_knowledge_base, RealLLM())
directly from _handle_policy_question instead of the offline path.

NOTE: the retry cap here is hardcoded to 1, intentionally -- proper
bounded-retry / stopping-criteria policy is separate, later material.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# 1. Draft an answer from retrieved chunks
# ---------------------------------------------------------------------------

ANSWER_PROMPT = """\
Answer the question using ONLY the context chunks below. If the chunks
don't contain the answer, say so plainly instead of guessing.

Question: {query}

Context chunks:
{chunks}

Answer:
"""


@dataclass
class Draft:
    query: str
    answer: str
    chunks: list[str]


def build_draft_answer(query: str, search_tool, llm, top_k: int = 3) -> Draft:
    hits = search_tool(query, top_k)
    chunks = [chunk for chunk, _score in hits]
    formatted = "\n".join(f"- {c}" for c in chunks)
    answer = llm.complete(ANSWER_PROMPT.format(query=query, chunks=formatted))
    return Draft(query=query, answer=answer, chunks=chunks)


# Critique: is every claim in the draft actually backed by the chunks?

CRITIQUE_PROMPT = """\
Question: {query}
Draft answer: {answer}
Context chunks used:
{chunks}

Is every claim in the draft answer directly supported by the context
chunks above? Reply with exactly one line:
PASS
or
FAIL: <short reason, and what a better search query would look like>
"""


@dataclass
class Critique:
    passed: bool
    reason: str
    suggested_query: str | None


def critique_answer(draft: Draft, llm) -> Critique:
    formatted_chunks = "\n".join(f"- {c}" for c in draft.chunks)
    verdict = llm.complete(
        CRITIQUE_PROMPT.format(query=draft.query, answer=draft.answer, chunks=formatted_chunks)
    ).strip()

    if verdict.upper().startswith("PASS"):
        return Critique(passed=True, reason="", suggested_query=None)

    # naive parse of "FAIL: reason ... query: ..." — good enough for this assignment
    reason = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict
    return Critique(passed=False, reason=reason, suggested_query=None)


# The guardrail: draft -> critique -> ONE retry -> final answer

def answer_with_grounding_check(query: str, search_tool, llm, top_k: int = 3) -> str:
    draft = build_draft_answer(query, search_tool, llm, top_k=top_k)
    critique = critique_answer(draft, llm)

    if critique.passed:
        return draft.answer

    # exactly one retry, using the critique to reformulate the search
    retry_query = critique.suggested_query or f"{query} (be more specific: {critique.reason})"
    retry_draft = build_draft_answer(retry_query, search_tool, llm, top_k=top_k)
    retry_critique = critique_answer(retry_draft, llm)

    if retry_critique.passed:
        return retry_draft.answer

    return "I couldn't find a grounded answer to this in the knowledge base."


# ---------------------------------------------------------------------------
# Real implementations (TODOs resolved)
# ---------------------------------------------------------------------------

class RealLLM:
    """Wraps rag/generate.py's real Anthropic client to match this
    module's llm.complete(prompt) -> str shape. Requires ANTHROPIC_API_KEY
    with available credits in the repo root .env."""

    def complete(self, prompt: str) -> str:
        from generate import client, MODEL

        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


def real_search_knowledge_base(query: str, top_k: int = 3):
    """Wraps rag/agentic_rag.py's real retrieval (winner per
    retrieval_eval's comparison table) to match this module's
    search_tool(query, top_k) -> list[(text, score)] shape."""
    from agentic_rag import agentic_rag_search
    from vector_store import get_client, get_or_create_collection
    from hybrid_rag import build_bm25_index

    vs_client = get_client()
    collection = get_or_create_collection(vs_client)
    bm25_index, chunks = build_bm25_index()

    retrieved, _reasoning_log = agentic_rag_search(
        collection, bm25_index, chunks, query, n_results=top_k
    )
    return [(chunk.text, score) for chunk, score in retrieved]


# ---------------------------------------------------------------------------
# Fake stand-ins kept for the standalone demo below (no API key needed)
# ---------------------------------------------------------------------------

class FakeLLM:
    def __init__(self):
        self._calls = 0

    def complete(self, prompt: str) -> str:
        self._calls += 1
        if prompt.startswith("Answer the question"):
            if "pet grooming" in prompt.lower():
                if self._calls <= 2:
                    return "We offer free pet grooming with every booking."
                return "We don't offer pet grooming; only boarding and daycare are covered."
        if prompt.startswith("Question:"):
            if "free pet grooming" in prompt:
                return "FAIL: no chunk mentions grooming, only boarding/daycare"
            return "PASS"
        return "PASS"


def fake_search_knowledge_base(query: str, top_k: int = 3):
    fake_kb = {
        "does the company offer pet grooming?": [
            ("We offer overnight boarding and daytime daycare for pets.", 0.62),
        ],
    }
    return fake_kb.get(query.lower(), [("We offer overnight boarding and daytime daycare for pets.", 0.4)])[:top_k]


# Demo: first draft fails the grounding check, retry corrects it

if __name__ == "__main__":
    llm = FakeLLM()
    demo_query = "Does the company offer pet grooming?"

    draft = build_draft_answer(demo_query, fake_search_knowledge_base, llm)
    print("Draft:", draft.answer)

    critique = critique_answer(draft, llm)
    print("Passed:", critique.passed, "| Reason:", critique.reason)

    final = answer_with_grounding_check(demo_query, fake_search_knowledge_base, llm)
    print("Final answer:", final)