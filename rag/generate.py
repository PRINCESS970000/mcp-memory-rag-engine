import os
from pathlib import Path
from datetime import date

import anthropic
from dotenv import load_dotenv

from chunk_schema import PolicyChunk

# Load ANTHROPIC_API_KEY from the .env file at the repo root
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"


def generate_answer(
    question: str,
    retrieved_chunks: list[PolicyChunk],
    llm
) -> str:
    """
    Generates an answer using ONLY the retrieved chunks as context.
    """

    context = "\n\n".join(
        f"[{c.document_id} — Section {c.section_id}: {c.section_title}]\n{c.text}"
        for c in retrieved_chunks
    )

    prompt = f"""You are answering a question using ONLY the policy excerpts below.

If the excerpts do not contain enough information to answer, say so explicitly --
do not use any outside knowledge.

POLICY EXCERPTS:
{context}

QUESTION: {question}

Answer concisely, and cite the section number(s) you used."""

    return llm.complete(prompt)

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 1. Data Classes & Prompts
# ---------------------------------------------------------------------------

@dataclass
class Draft:
    query: str
    answer: str
    chunks: list[PolicyChunk]


@dataclass
class Critique:
    passed: bool
    reason: str
    suggested_query: str | None


CRITIQUE_PROMPT = """\
Question: {query}
Draft answer: {answer}

Policy Excerpts used:
{chunks}

Is every claim in the draft answer directly supported by the policy excerpts above?
Reply with exactly one line in this format:
PASS
or
FAIL: <short reason, and what a better search query would look like>
"""


# ---------------------------------------------------------------------------
# 2. Fake Search Function (دالة البحث الوهمية للاختبار)
# ---------------------------------------------------------------------------

def fake_search_knowledge_base(query: str, top_k: int = 3) -> list[PolicyChunk]:
    """Fake search tool that returns PolicyChunk objects for testing."""

    fake_db = {
        "does the company offer pet grooming?": [
            PolicyChunk(
                chunk_id="CHUNK-001",
                document_id="DOC-101",
                policy_type="Pet Care",
                section_id="3.1",
                section_title="Pet Care Services",
                text="We offer overnight boarding and daytime daycare for pets.",
                last_reviewed_date=date(2026, 1, 1),
                version="1.0",
            )
        ]
    }

    default_chunk = PolicyChunk(
        chunk_id="CHUNK-001",
        document_id="DOC-101",
        policy_type="Pet Care",
        section_id="3.1",
        section_title="Pet Care Services",
        text="We offer overnight boarding and daytime daycare for pets.",
        last_reviewed_date=date(2026, 1, 1),
        version="1.0",
    )

    return fake_db.get(
        query.lower(),
        [default_chunk]
    )[:top_k]

# ---------------------------------------------------------------------------
# 3. Critique Step & Main Guardrail
# ---------------------------------------------------------------------------

def critique_answer(draft: Draft, llm) -> Critique:
    formatted_chunks = "\n\n".join(
        f"[{c.document_id} — Section {c.section_id}: {c.section_title}]\n{c.text}"
        for c in draft.chunks
    )

    prompt = CRITIQUE_PROMPT.format(
        query=draft.query,
        answer=draft.answer,
        chunks=formatted_chunks
    )

    verdict = llm.complete(prompt).strip()

    if verdict.upper().startswith("PASS"):
        return Critique(
            passed=True,
            reason="",
            suggested_query=None
        )

    reason = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict

    return Critique(
        passed=False,
        reason=reason,
        suggested_query=None
    )


def answer_with_grounding_check(
    query: str,
    search_tool,
    llm,
    top_k: int = 3
) -> str:

    # First search
    initial_chunks = search_tool(query, top_k=top_k)

    # Generate first draft
    draft_text = generate_answer(
        query,
        initial_chunks,
        llm
    )

    draft = Draft(
        query=query,
        answer=draft_text,
        chunks=initial_chunks
    )

    # First grounding check
    critique = critique_answer(draft, llm)

    print("\nFirst Critique:")
    print("PASS" if critique.passed else "FAIL")
    if critique.reason:
        print("Reason:", critique.reason)

    if critique.passed:
        return draft.answer

    # ONE retry only
    retry_query = (
        critique.suggested_query
        or f"{query} (be more specific: {critique.reason})"
    )

    print("\nRetry Query:")
    print(retry_query)

    retry_chunks = search_tool(
        retry_query,
        top_k=top_k
    )

    retry_text = generate_answer(
        query,
        retry_chunks,
        llm
    )

    retry_draft = Draft(
        query=query,
        answer=retry_text,
        chunks=retry_chunks
    )

    # Second grounding check
    retry_critique = critique_answer(
        retry_draft,
        llm
    )

    print("\nRetry Critique:")
    print("PASS" if retry_critique.passed else "FAIL")

    if retry_critique.passed:
        return retry_draft.answer

    return "I couldn't find a grounded answer to this in the knowledge base."

class FakeLLM:

    def __init__(self):
        self.answer_calls = 0
        self.critique_calls = 0

    def complete(self, prompt: str) -> str:

        # Answer generation
        if prompt.startswith("You are answering"):
            self.answer_calls += 1

            # First answer is intentionally wrong
            if self.answer_calls == 1:
                return "Yes, the company offers pet grooming."

            # Retry answer is grounded
            return (
                "The policy does not mention pet grooming. "
                "It only mentions overnight boarding and daytime daycare "
                "(Section 3.1)."
            )

        # Critique
        if prompt.startswith("Question:"):
            self.critique_calls += 1

            # First critique fails
            if self.critique_calls == 1:
                return (
                    "FAIL: the retrieved chunk mentions boarding and "
                    "daycare, but does not mention pet grooming."
                )

            # Retry critique passes
            return "PASS"

        return "PASS"
# ---------------------------------------------------------------------------
# 4. Demo Execution (تشغيل وتجربة الفانكشن الفيك)
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    demo_query = "Does the company offer pet grooming?"

    fake_llm = FakeLLM()

    final_answer = answer_with_grounding_check(
        query=demo_query,
        search_tool=fake_search_knowledge_base,
        llm=fake_llm,
        top_k=3
    )

    print("\n" + "=" * 50)
    print("FINAL ANSWER:")
    print(final_answer)
    print("=" * 50)