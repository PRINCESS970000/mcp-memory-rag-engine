"""
Deterministic, LLM-free stand-in for generation and support verification.

LIMITATION (documented honestly, same spirit as context_eval's extractive
summarizer caveat): this cannot catch a hallucination phrased in different
words from the source, because it never actually generates new phrasing --
it only extracts and recombines sentences that already exist in the
retrieved chunks. A real LLM call (Anthropic or Ollama) is a strictly
stronger check and should replace this once API credits or a stable
network connection are available -- see generate.py / self_rag_check.py
for the real-LLM versions this is standing in for.
"""

import re

from chunk_schema import PolicyChunk

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "what", "which", "who",
    "does", "do", "did", "can", "could", "will", "would", "should",
    "of", "to", "in", "on", "for", "and", "or", "if", "be", "must",
    "this", "that", "with", "as", "at", "by", "from", "it", "how",
}


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def generate_answer_extractive(question: str, retrieved_chunks: list[PolicyChunk]) -> str:
    """
    Picks the sentences (across all retrieved chunks) that share the most
    keywords with the question, and returns them verbatim with their
    section citation -- an answer built entirely out of retrieved text.
    """
    if not retrieved_chunks:
        return "No relevant policy content was retrieved for this question."

    question_words = _keywords(question)
    scored_sentences = []

    for chunk in retrieved_chunks:
        sentences = re.split(r'(?<=[.!?])\s+', chunk.text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            overlap = len(_keywords(sentence) & question_words)
            if overlap > 0:
                scored_sentences.append((overlap, chunk, sentence))

    if not scored_sentences:
        return (
            "The retrieved policy excerpts do not contain enough matching "
            "information to answer this question directly."
        )

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    top = scored_sentences[:3]

    lines = [
        f'"{sentence}" (Section {chunk.section_id})'
        for _score, chunk, sentence in top
    ]
    return " ".join(lines)

def check_support_extractive(answer: str, retrieved_chunks: list[PolicyChunk]) -> tuple[bool, str]:
    """
    LLM-free support check: verifies that the meaningful words in the
    answer actually appear in the retrieved source text.

    LIMITATION: this is a WEAKER check than the real LLM judge in
    self_rag_check.py -- it confirms word-level presence, not that the
    logical claim being made is actually true given the source. It
    cannot catch a hallucination that reuses source vocabulary but
    draws a false conclusion from it. Use the real check_support() in
    self_rag_check.py whenever API access is available.
    """
    source_text = " ".join(c.text for c in retrieved_chunks)
    source_words = _keywords(source_text)
    answer_words = _keywords(answer)

    if not answer_words:
        return False, "Answer contained no checkable content."

    unsupported = answer_words - source_words
    coverage = 1 - (len(unsupported) / len(answer_words))

    if coverage < 0.7:
        return False, (
            f"Only {coverage:.0%} of the answer's key terms appear in the "
            f"retrieved source text. Unmatched terms: {unsupported}"
        )
    return True, f"{coverage:.0%} of the answer's key terms are grounded in the retrieved source."