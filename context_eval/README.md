# context_eval/

(placeholder — work in progress for the Memory & RAG lab)
# Context Window Management — Brightpeak Academy Advising Agent

## The real problem
Brightpeak's advising agent runs long multi-turn sessions where an advisor
pulls student profiles, course catalogs, grades, and reports across dozens
of tool calls per call. A disciplinary flag ("student was expelled for
documented cheating, any future enrollment needs disciplinary-committee
sign-off") can get mentioned once early in the session, then buried under
routine tool-call traffic for the rest of the call. If that flag doesn't
survive to the point where the advisor asks "can we enroll this student in
a new course?", the agent gives a materially wrong, policy-violating
answer. That's a real cost, not a toy scenario — which is why this needs a
real evaluated context strategy, not a guess.

## Test design
- **10-run long-context suite** (`transcript_builder.py`), each run
  35–55 filler exchanges (~150–220 turns) built from **real output of the
  6 existing MCP tools** (`tool_samples.py`, run against an expanded mock
  DB matching the actual `mcp_server/` schema — 15 students, 10 courses).
  This produces **~5,000–8,000 tokens of realistic input per run**,
  deliberately leaning on large tool-output volume rather than trying to
  inflate model output (input tokens are the cheap, high-volume cost
  driver; output tokens are the expensive one — no reason to burn budget
  generating filler).
- The critical disciplinary detail is planted in turn 2, as **plain prose
  from the user, not inside a tool result** — the harder, more realistic
  case, since important facts don't always arrive as structured data.
- Each run ends with a question that can only be answered correctly if the
  flag survived: *"Student X wants to enroll in Machine Learning next
  term — can we go ahead?"*
- After each of the 4 strategies compacts the transcript, a generation
  step (`generate_step.py`) produces the agent's actual answer **grounded
  only in what survived compaction** — so we score real task accuracy, not
  just "is the fact string present somewhere."

## Results (10 runs)

| Strategy | Accuracy (10 runs) | Avg. input tokens/run | Avg. output tokens/run | Avg. latency |
|---|---|---|---|---|
| Sliding window (last N turns) | 0/10 | 714 | 23 | 0.0s |
| Observation masking (mask old tool results) | 10/10 | 3,186 | 35 | 0.0s |
| Recursive summarization (chunked compaction) | 10/10 | 756 | 35 | 0.0002s |
| Zone-based pruning (critical + recent zones) | 10/10 | 2,180 | 35 | 0.0002s |

## Decision

**Sliding window is disqualified outright** — 0/10 accuracy. It has no
mechanism to protect anything outside the recency window, so the
disciplinary flag is gone in every single run. Cheap and fast is
irrelevant when the agent is confidently wrong.

Among the three strategies that hit 10/10 accuracy, **recursive
summarization ships** — it reaches the same perfect accuracy as
observation masking and zone-based pruning at roughly **a quarter of the
input-token cost** (756 vs. 2,180–3,186 tokens/run), because it actually
compresses the routine tool-call bulk instead of just relocating or
masking it. Observation masking and zone-based pruning both keep large
swaths of the transcript verbatim (recent turns / recent tool results),
which is what keeps their token cost high even though their accuracy is
identical.

**Caveat we're keeping honest in the report:** our summarizer here is a
deterministic keyword-anchored extractive function, not a live LLM
summarization call (no model access in the eval sandbox). It's guaranteed
to preserve anything matching our critical-keyword list, which is a more
favorable condition than a real LLM summarizer gets — a real one could
drop the detail during compaction with no such guarantee. **Production
recommendation:** ship recursive summarization for the token savings, but
pin disciplinary/compliance-flagged facts into a protected zone (borrowing
zone-based pruning's mechanism) so they're never subject to the
summarizer's judgment at all — a hybrid, not a pure single strategy.

## Files
- `tool_samples.py` — real outputs from the 6 existing MCP tools against an
  expanded mock DB (matches `mcp_server/`'s schema)
- `transcript_builder.py` — builds the 10-run long-context test suite
- `strategies.py` — all 4 implementations: sliding window, observation
  masking, recursive summarization, zone-based pruning
- `generate_step.py` — grounded answer generation from compacted context
  (drives the task-accuracy metric)
- `benchmark.py` — runs the suite, prints the comparison table (plain +
  markdown for direct README embedding)