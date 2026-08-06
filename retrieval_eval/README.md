# retrieval_eval/

## The problem this solves
BrightPeak's `db/` tables store *facts* (a student's enrollment status, a
grade, a certificate code) but not *rules* — things like "when can a
student re-enroll after being dropped three times" or "who is allowed to
approve a grade appeal." Those rules live in policy documents
(`policies/`), not in any MCP tool. Without retrieval, an agent asked
about these rules would have to guess or hallucinate an answer.

## Test set
12 questions in `test_questions.py`, 4 per category:
- **general** — answerable from one passage, no section number needed.
- **citation** — names an exact section number (e.g. "Section 3.2").
  Section numbers don't embed distinctively, so this category is meant to
  favor hybrid search over naive vector search.
- **multi_hop** — needs two chunks from two different policy documents,
  connected by an explicit cross-reference (e.g. "see the Grading
  Permissions Policy, Section 3"). Meant to favor agentic RAG, which
  follows those cross-references as a second retrieval hop instead of
  re-searching blindly.

Each question's `expected_chunk_ids` was verified against the actual
ingested chunks before being trusted (see the debugging story below —
one of our own expected answers turned out to be wrong).

## Final comparison table

| Architecture | Accuracy | General | Citation | Multi-hop | Avg Latency |
|---|---|---|---|---|---|
| Naive RAG | 9/12 (75%) | 3/4 | 4/4 | 2/4 | 0.30s |
| Hybrid search (vector + BM25, RRF) | 8/12 (67%) | 4/4 | 3/4 | 1/4 | 0.29s |
| **Agentic RAG** | **12/12 (100%)** | 4/4 | 4/4 | 4/4 | 0.28s |

*(Latency measured for retrieval only, not generation. Token usage
requires a live `--generate` run against the Anthropic API, which needs
account credits we didn't have available for this evaluation — the
`--generate` flag and the token-counting code are implemented and ready
to run once credits are available.)*

## What we shipped, and why
**Agentic RAG.** It won outright on every category, including the ones
it wasn't specifically built to win — and it was also the fastest of the
three. That last part isn't a coincidence: instead of re-searching for a
second hop, it follows a cross-reference and fetches the target chunk
directly by ID, which is cheaper than another full similarity search.

Hybrid search underperformed naive RAG overall (8/12 vs 9/12), which is
the opposite of what we expected going in. With only 29 chunks in a
narrow, similarly-worded policy corpus, mixing in BM25 rankings via RRF
sometimes pulled the correct chunk below the top-3 cutoff even when pure
vector search alone would have found it. This is a real result from our
own test suite, not a hypothetical — see the debugging log below for how
we found it.

## Debugging log (the real conflicts this system surfaced)

**1. Unidirectional cross-references broke multi-hop retrieval.**
Our first full run scored agentic RAG at 9/12, missing every multi-hop
question that required "hopping backward." We traced it to
`POL-GP-005_s3` (Grading Permissions) referencing `POL-RE-001_s3.2`
(Re-Enrollment), but not the reverse. If retrieval landed on
`POL-RE-001_s3.2` first, agentic RAG had no cross-reference to follow and
never discovered the related rule in the other document. **Fix:**
`ingest.py`'s `load_all_policies()` now makes every cross-reference
bidirectional at load time. This alone raised agentic RAG from 9/12 to
11/12.

**2. A genuinely missing cross-reference, not a code bug.**
The last failing question (M4, about a conflict-of-interest scenario)
revealed that our own policy text never actually linked "who may resolve
an appeal" to the conflict-of-interest rule — the connection existed in
our heads when we wrote the test question, but not in the document. We
added the missing sentence to `grade_appeal_policy.md` Section 5. This
took agentic RAG to 12/12.

**3. A stale test file cost us a full debugging cycle.**
Early on, `run_comparison.py` reported nearly total failure (1/12) across
all three architectures. The cause wasn't the retrieval code — it was
that an old copy of `test_questions.py` (referencing policy IDs we'd
already deleted, like `POL-LOA-004`) had been copied into the repo
instead of the current one. Lesson: when multiple downloaded copies of
the same filename exist, always verify file contents (`grep`) before
assuming a "logic bug."

## Self-RAG-style verification
`rag/self_rag_check.py` implements two independent checks, run after
retrieval and after generation:
- **Relevance check** (`check_relevance`) — free, no LLM call. Fails if
  nothing was retrieved, or if the top result's similarity score is below
  a floor (0.35), which catches the "returned the 3 least-bad chunks
  anyway" failure mode of top-k retrieval on an off-topic question.
  Verified directly against mocked strong/weak/empty result sets.
- **Support check** (`check_support`) — a second, separate LLM call whose
  only input is the generated answer and the retrieved source text, never
  the original question, so it can't rubber-stamp a plausible-sounding
  but ungrounded answer.

If either check fails, `flag_if_unsupported()` ensures the raw answer is
never passed through silently — it's wrapped with an explicit
`[UNVERIFIED]` flag and the failure reason.

## How to reproduce
```bash
cd rag
python build_index.py                        # (re)builds the Chroma index from policies/
cd ..
python retrieval_eval/run_comparison.py       # retrieval-only, free
python retrieval_eval/run_comparison.py --generate   # also generates answers and counts real tokens (uses API credits)
```
