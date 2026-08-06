import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from chunk_schema import PolicyChunk

# Load ANTHROPIC_API_KEY from the .env file at the repo root
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"


def generate_answer(question: str, retrieved_chunks: list[PolicyChunk]) -> str:
    """
    Generates an answer using ONLY the retrieved chunks as context.
    The prompt explicitly instructs the model to say so if the chunks
    don't contain the answer, rather than filling gaps from its own knowledge --
    this is what makes the later Self-RAG support check meaningful to run.
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

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
