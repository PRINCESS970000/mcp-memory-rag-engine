"""
Self-RAG-style verification, applied AFTER retrieval and AFTER generation.

The generate.py prompt already instructs the model to say "the excerpts
don't contain enough information" if the retrieved chunks don't actually
answer the question, rather than filling gaps from outside knowledge. This
module is the explicit check layer described in the lab: instead of
trusting that instruction blindly, we verify it actually held, using two
independent checks:

1. Relevance check -- is what we retrieved actually about the question?
2. Support check -- is the generated answer actually backed by the
   retrieved text?
"""

from dataclasses import dataclass

import anthropic
from chunk_schema import PolicyChunk

RELEVANCE_SCORE_FLOOR = 0.35


@dataclass
class VerificationResult:
    relevance_passed: bool
    relevance_reason: str
    support_passed: bool
    support_reason: str

    @property
    def passed(self) -> bool:
        return self.relevance_passed and self.support_passed


def check_relevance(
    question: str,
    retrieved: list[tuple[PolicyChunk, float]],
) -> tuple[bool, str]:
    """
    Cheap relevance check.
    """
    if not retrieved:
        return False, "No chunks were retrieved at all."

    top_chunk, top_score = retrieved[0]

    if top_score < RELEVANCE_SCORE_FLOOR:
        return (
            False,
            f"Top result ({top_chunk.chunk_id}) scored {top_score:.3f}, "
            f"below the relevance floor of {RELEVANCE_SCORE_FLOOR}. "
            f"Retrieval likely found nothing genuinely relevant.",
        )

    return (
        True,
        f"Top result ({top_chunk.chunk_id}) scored {top_score:.3f}, "
        "above the relevance floor.",
    )


def check_support(
    answer: str,
    retrieved: list[tuple[PolicyChunk, float]],
) -> tuple[bool, str]:
    """
    Uses Claude to verify that the generated answer is supported
    by the retrieved policy chunks.
    """
    from generate import client, MODEL

    context = "\n\n".join(
        f"[{c.document_id} — Section {c.section_id}]\n{c.text}"
        for c, _score in retrieved
    )

    judge_prompt = f"""You are a strict fact-checker.

Below is a SOURCE TEXT and a CLAIM.

Decide whether the CLAIM is fully supported by the SOURCE TEXT alone.

Reply using exactly this format:

SUPPORTED
Reason...

or

UNSUPPORTED
Reason...

SOURCE TEXT:
{context}

CLAIM:
{answer}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": judge_prompt,
                }
            ],
        )

        verdict_text = response.content[0].text.strip()

        lines = verdict_text.split("\n", 1)
        verdict = lines[0].strip().upper()
        reason = lines[1].strip() if len(lines) > 1 else ""

        passed = verdict.startswith("SUPPORTED")

        return passed, reason or verdict_text

    except anthropic.BadRequestError as e:
        print(f"Anthropic API Error: {e}")
        return (
            False,
            "Support verification skipped because the Anthropic API has no available credits.",
        )

    except Exception as e:
        print(f"Unexpected Error: {e}")
        return (
            False,
            f"Support verification failed: {e}",
        )


def verify(
    question: str,
    answer: str,
    retrieved: list[tuple[PolicyChunk, float]],
) -> VerificationResult:

    relevance_passed, relevance_reason = check_relevance(
        question,
        retrieved,
    )

    support_passed, support_reason = check_support(
        answer,
        retrieved,
    )

    return VerificationResult(
        relevance_passed=relevance_passed,
        relevance_reason=relevance_reason,
        support_passed=support_passed,
        support_reason=support_reason,
    )


def flag_if_unsupported(
    result: VerificationResult,
    answer: str,
) -> str:

    if result.passed:
        return answer

    reasons = []

    if not result.relevance_passed:
        reasons.append(
            f"relevance check failed: {result.relevance_reason}"
        )

    if not result.support_passed:
        reasons.append(
            f"support check failed: {result.support_reason}"
        )

    return (
        "[UNVERIFIED — do not trust this answer without human review]\n\n"
        f"Reason(s): {'; '.join(reasons)}\n\n"
        f"Original answer:\n{answer}"
    )