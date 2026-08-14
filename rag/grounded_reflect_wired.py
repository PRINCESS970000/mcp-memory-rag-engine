"""
Grounding check + one-retry guardrail, wired to our real naive_rag_search
and the real Anthropic client from generate.py.

Flow: draft answer from retrieved chunks -> critique (is every claim
actually backed by the chunks?) -> if FAIL, retry the search exactly
ONCE with a reformulated query -> critique again -> if still FAIL, say
so honestly instead of guessing.
"""

from dataclasses import dataclass

from generate import client, MODEL
from naive_rag import naive_rag_search


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


def call_llm(prompt: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def search_knowledge_base(query: str, top_k: int = 3):
    """
    Wraps our real naive_rag_search so it matches the (query, top_k) ->
    list[(chunk_text, score)] shape this module expects, using the real
    Chroma collection.
    """
    from vector_store import get_client, get_or_create_collection

    coll = get_or_create_collection(get_client())
    results = naive_rag_search(coll, query, n_results=top_k)
    return [(chunk.text, score) for chunk, score in results]


def build_draft_answer(query: str, search_tool, llm, top_k: int = 3) -> Draft:
    hits = search_tool(query, top_k)
    chunks = [chunk for chunk, _score in hits]
    formatted = "\n".join(f"- {c}" for c in chunks)
    answer = llm(ANSWER_PROMPT.format(query=query, chunks=formatted))
    return Draft(query=query, answer=answer, chunks=chunks)


# ---------------------------------------------------------------------------
# 2. Critique: is every claim in the draft actually backed by the chunks?
# ---------------------------------------------------------------------------

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
    verdict = llm(
        CRITIQUE_PROMPT.format(query=draft.query, answer=draft.answer, chunks=formatted_chunks)
    ).strip()

    if verdict.upper().startswith("PASS"):
        return Critique(passed=True, reason="", suggested_query=None)

    reason = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict
    return Critique(passed=False, reason=reason, suggested_query=None)


# ---------------------------------------------------------------------------
# 3. The guardrail: draft -> critique -> ONE retry -> final answer
# ---------------------------------------------------------------------------

def answer_with_grounding_check(query: str, search_tool=search_knowledge_base, llm=call_llm, top_k: int = 3) -> str:
    draft = build_draft_answer(query, search_tool, llm, top_k=top_k)
    critique = critique_answer(draft, llm)

    if critique.passed:
        return draft.answer

    retry_query = critique.suggested_query or f"{query} (be more specific: {critique.reason})"
    retry_draft = build_draft_answer(retry_query, search_tool, llm, top_k=top_k)
    retry_critique = critique_answer(retry_draft, llm)

    if retry_critique.passed:
        return retry_draft.answer

    return "I couldn't find a grounded answer to this in the knowledge base."


# ---------------------------------------------------------------------------
# Demo: a question our policy corpus doesn't cover, so the first draft
# should fail grounding, and the retry should honestly say so.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo_query = "Does BrightPeak offer a tuition refund if I withdraw?"

    draft = build_draft_answer(demo_query, search_knowledge_base, call_llm)
    print("Draft:", draft.answer)

    critique = critique_answer(draft, call_llm)
    print("Passed:", critique.passed, "| Reason:", critique.reason)

    final = answer_with_grounding_check(demo_query)
    print("Final answer:", final)
