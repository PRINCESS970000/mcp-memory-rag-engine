# agent/

## What this connects
This is the integration layer that ties together the three systems built
separately in `memory/`, `rag/`, and `context_eval/` into one working
agent loop, reusing all three as-is (no duplication) plus the existing
`mcp_server/` tools.

```
user message
     │
     ▼
intent_router.route_intent()  ──► "policy" | "memory" | "db_tool"
     │
     ├─ policy ──► rag/agentic_rag_search() ──► generate_local.py ──► support/relevance check
     ├─ memory ──► memory/self_check.recall_with_verification()
     └─ db_tool ─► existing mcp_server/ tools (not yet wired, see Known gaps)
     │
     ▼
every message (in + out) added to memory/short_term.ShortTermMemory
buffer checked against overflow threshold ──► context_eval.recursive_summarization()
```

## Real integration bugs found while wiring this together

Nothing below was a design decision made up front — each was discovered
by actually running the connected pieces and watching them fail.

### 1. `agent/router.py` collided with `memory/router.py`
Both files were named `router.py` before integration, doing completely
different jobs (agent-level intent routing vs. memory's promote-or-drop
routing). Adding both their parent folders to `sys.path` meant Python
would silently import whichever one it found first, shadowing the other.
**Fix:** renamed the agent-level file to `intent_router.py`. The two
`route_*` functions are not interchangeable and were never meant to be —
this was purely a naming collision, not a logic conflict.

### 2. Relevance floor calibrated for the wrong score scale
`rag/self_rag_check.py`'s `check_relevance()` was calibrated against
`naive_rag`'s cosine similarity scores (typically 0.6–0.8 for a good
match, floor set at 0.35). But `_handle_policy_question` uses
**agentic RAG**, whose scores come from Reciprocal Rank Fusion
(`1 / (60 + rank)`), which tops out around 0.03. Reusing the 0.35 floor
against RRF scores rejected every single agentic result as "irrelevant,"
even a correct top-1 match. **Fix:** a separate `AGENTIC_RELEVANCE_FLOOR
= 0.01`, calibrated for the RRF scale, used only for agentic RAG results.
This is a genuine lesson for anyone combining retrieval architectures
with different scoring systems behind one verification threshold — the
check must be re-calibrated per score type, not reused blindly.

### 3. No live LLM access in this environment
Real generation (`rag/generate.py`) and the real LLM-based support check
(`rag/self_rag_check.py`'s `check_support`) both require Anthropic API
credits, which weren't available while building this integration (no
billing set up, and network conditions ruled out a local Ollama model as
a practical alternative here). **Workaround:** `agent/generate_local.py`
implements an LLM-free extractive generator (picks and returns the
retrieved sentences with the most keyword overlap with the question) and
an LLM-free support check (keyword-coverage between answer and source).
**Honest limitation:** this cannot catch a hallucination phrased in
different words than the source, since it never generates new phrasing —
only recombines existing sentences. It also cannot judge whether a
*logical conclusion* drawn from the source is actually valid. Swap
`generate_local.generate_answer_extractive` / `check_support_extractive`
for `rag.generate.generate_answer` / `rag.self_rag_check.check_support`
once API access is available — `_handle_policy_question` needs no other
change, since both pairs share the same function signatures.

## Known gaps (not yet resolved)

- **`_maybe_compact_buffer` computes but does not write back.** It calls
  `context_eval.recursive_summarization()` correctly and prints what the
  compacted buffer would look like, but `memory/short_term.py`'s buffer
  is backed by `mcp_server/server.py`'s `messages` table via
  `store_message()` / `get_chat_history()`, which currently has no
  function to replace stored messages with a compacted version. Wiring
  this properly needs a short conversation with whoever owns
  `mcp_server/server.py`, not a unilateral change to their file.
- **`db_tool` intent is not wired to the existing MCP tools yet.** It
  currently returns a placeholder string. This is the most mechanical of
  the three routing branches (the tools already exist and are already
  tested from the earlier MCP Server Lab) and is the next piece planned.

## How to run the demo

```bash
cd memory
python reset_memory_tables.py
python run_kareem_story.py        # seeds a real semantic fact + conflict history for student 7

cd ../rag
python build_index.py             # (re)builds the Chroma index from policies/

cd ../agent
python -c "
from loop import handle_message
from short_term import ShortTermMemory

stm = ShortTermMemory(session_id='demo_session', student_id=7)

r1 = handle_message(stm, student_id=7, message='What are the valid grounds for filing a grade appeal?')
print('--- POLICY QUESTION ---')
print('Intent:', r1['intent'])
print('Answer:', r1['answer'])
print('Verification:', r1['verification'])

r2 = handle_message(stm, student_id=7, message='What did we decide last time about my re-enrollment?')
print()
print('--- MEMORY QUESTION ---')
print('Intent:', r2['intent'])
print('Answer:', r2['answer'])
print('Memory status:', r2['memory_status'])
"
```

## Files
- `intent_router.py` — top-level routing: policy / memory / db_tool
- `loop.py` — `handle_message()`, the main entry point, plus the three
  per-intent handlers
- `generate_local.py` — LLM-free generation + support check (temporary
  stand-in for `rag/generate.py` + `rag/self_rag_check.check_support`,
  see limitation above)
