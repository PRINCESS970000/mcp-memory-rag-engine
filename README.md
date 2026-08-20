# BrightPeak Academy — Memory & RAG Engine

Extension of the existing `mcp_server/` and `db/` (from the MCP Server Lab)
with a long-term memory system and a document-grounded retrieval system,
wired together into one agent loop.

## The problem

BrightPeak's registration MCP server already answers factual questions
against real tables (`students`, `courses`, `enrollments`, `certificates`).
Two gaps showed up once we looked at real usage:

1. **No memory across sessions.** A registration decision made in one
   conversation (e.g. an admin overturning a re-enrollment approval) is
   gone the next time a student asks about it — the agent has to be
   re-told the same history every time.
2. **No grounding for policy questions.** Rules like "what counts as
   valid grounds for a grade appeal" or "who can approve re-enrollment
   after three drops" live only in policy text, never in a table or an
   MCP tool. Without retrieval, the agent would have to guess.

Both gaps have a real cost: a wrong memory recall or a hallucinated
policy answer is a wrong administrative decision, not a cosmetic bug.

## Architecture

```
user message
     │
     ▼
intent_router.route_intent()  ──► "policy" | "memory" | "db_tool"
     │
     ├─ policy  ──► rag/agentic_rag_search() ──► generate ──► Self-RAG check
     ├─ memory  ──► memory/self_check.recall_with_verification()
     └─ db_tool ──► existing mcp_server/ tools (reused, not duplicated)
     │
     ▼
every message logged to memory/short_term.ShortTermMemory
buffer overflow ──► context_eval's recursive_summarization()
```

## Results

### Context management (`context_eval/`) — full report in `context_eval/README.md`

| Strategy | Accuracy (10 runs) | Avg input tokens | Avg latency |
|---|---|---|---|
| Sliding window | 0/10 | 714 | 0.0s |
| Observation masking | 10/10 | 3,186 | 0.0s |
| **Recursive summarization** | **10/10** | **756** | 0.0002s |
| Zone-based pruning | 10/10 | 2,180 | 0.0002s |

**Shipped: recursive summarization** — same perfect accuracy as the two
other passing strategies, at roughly a quarter of the token cost.

### Retrieval architecture (`retrieval_eval/`) — full report in `retrieval_eval/README.md`

| Architecture | Accuracy | General | Citation | Multi-hop | Avg latency |
|---|---|---|---|---|---|
| Naive RAG | 9/12 | 3/4 | 4/4 | 2/4 | 0.30s |
| Hybrid search | 8/12 | 4/4 | 3/4 | 1/4 | 0.29s |
| **Agentic RAG** | **12/12** | 4/4 | 4/4 | 4/4 | 0.28s |

**Shipped: agentic RAG** — won every category and was the fastest of the
three, since it follows cross-references directly by ID instead of
re-searching. Two real bugs were found and fixed while building this
evaluation (unidirectional cross-references, and a genuinely missing
cross-reference in our own policy text) — full debugging log in
`retrieval_eval/README.md`.

### Memory (`memory/`) — full report in `memory/README.md`

Demonstrated with a real scenario (`run_kareem_story.py`): a re-enrollment
request is approved, then an admin later reverses the decision. The
consolidation layer detects the contradiction between the two episodic
events and resolves it — the old fact is versioned and superseded, not
silently overwritten:

```
{'status': 'conflict_resolved',
 'old_fact': 'CS101 re-enrollment: APPROVED ...',
 'new_fact': 'CS101 re-enrollment: DENIED ...',
 'superseded_fact_id': 1}
```

### Agent integration (`agent/`) — full report in `agent/README.md`

Three real integration bugs found by actually running the connected
pieces (not found by inspection):
1. `agent/router.py` silently shadowed `memory/router.py` on `sys.path`
   — renamed to `intent_router.py`.
2. `self_rag_check.py`'s relevance floor (0.35, calibrated for naive
   RAG's cosine similarity) rejected every agentic RAG result, since RRF
   fusion scores top out around 0.03 — added a separate floor calibrated
   for that scale.
3. **Intent misrouting** — `route_intent()` checked generic DB keywords
   (like "grade") before policy keywords, so "What are the valid grounds
   for filing a **grade** appeal?" was misrouted to a plain data lookup
   instead of retrieval. Fixed by reordering priority to
   `MEMORY > POLICY > DB_TOOL`, since policy keywords are more specific.
## 📑 Overview & Architecture

The planning subsystem receives task specifications and uses a **Routing Engine** to assign each subtask to the most suitable search and planning strategy:

1. **Plan-and-Solve (PS):** Zero-shot / single-pass decomposition for deterministic parsing, formatting, and mathematical constraint calculations.
2. **Tree of Thoughts (ToT):** Tree-based systematic search using beam-search evaluation and branch pruning for sequencing and ranking decisions under time/budget constraints.
3. **Language Agent Tree Search (LATS):** Monte Carlo Tree Search (MCTS) enhanced with environment trajectory feedback and value scoring for schedule optimization.

---

##  Summary of Execution Traces & Performance Metrics

Below is the summary of evaluation metrics collected across 9 representative test executions generated via `test_runner.py` using **Mistral AI**:

###  Overall Statistics

| Metric | Plan-and-Solve | Tree of Thoughts | LATS |
| --- | --- | --- | --- |
| **Tasks Processed** | 2 | 5 | 2 |
| **Avg Latency (s)** | ~1.71s | ~22.62s | ~4.39s |
| **Avg LLM Calls** | 1 | 9 | 2 |
| **Success Rate** | 100% | 100% | 100% |
| **Key Output Attribute** | Deterministic Tokens | 6 branches / 2 pruned | Best Score: ~0.93 |



###  Performance Breakdown by Algorithm

#### 1. Plan-and-Solve (Deterministic Parsing & Formatting)

* **LLM Calls:** 1 call per task
* **Average Latency:** $1.71 \text{ seconds}$
* **Average Tokens:** 386.5 total tokens ($175.5$ prompt + $211$ completion)
* **Behavior:** Highly efficient, lowest latency, ideal for low-complexity operational tasks.

#### 2. Tree of Thoughts (Course Sequencing & Path Ranking)

* **LLM Calls:** 9 calls per task
* **Average Latency:** $22.62 \text{ seconds}$
* **Branching Factor:** 6 generated branches, 2 pruned branches
* **Final Beam Size:** 2 optimal pathways retained
* **Behavior:** Deep reasoning with high coverage, ideal for multi-option trade-off analysis.

#### 3. LATS (Schedule Optimization with Environment Feedback)

* **LLM Calls:** 2 calls per task
* **Average Latency:** $4.39 \text{ seconds}$
* **Iterations Used:** 1 iteration
* **Best Reward Score:** Reached up to **0.933**
* **Behavior:** Environment-guided dynamic trajectory sampling, high accuracy for multi-constraint schedule optimization.

---

## 📑 Overview & Architecture

The planning subsystem receives task specifications and uses a **Routing Engine** to assign each subtask to the most suitable search and planning strategy:

1. **Plan-and-Solve (PS):** Zero-shot / single-pass decomposition for deterministic parsing, formatting, and mathematical constraint calculations.
2. **Tree of Thoughts (ToT):** Tree-based systematic search using beam-search evaluation and branch pruning for sequencing and ranking decisions under time/budget constraints.
3. **Language Agent Tree Search (LATS):** Monte Carlo Tree Search (MCTS) enhanced with environment trajectory feedback and value scoring for schedule optimization.

---

##  Summary of Execution Traces & Performance Metrics

Below is the summary of evaluation metrics collected across 9 representative test executions generated via `test_runner.py` using **Mistral AI**:

###  Overall Statistics

| Metric | Plan-and-Solve | Tree of Thoughts | LATS |
| --- | --- | --- | --- |
| **Tasks Processed** | 2 | 5 | 2 |
| **Avg Latency (s)** | ~1.71s | ~22.62s | ~4.39s |
| **Avg LLM Calls** | 1 | 9 | 2 |
| **Success Rate** | 100% | 100% | 100% |
| **Key Output Attribute** | Deterministic Tokens | 6 branches / 2 pruned | Best Score: ~0.93 |



###  Performance Breakdown by Algorithm

#### 1. Plan-and-Solve (Deterministic Parsing & Formatting)

* **LLM Calls:** 1 call per task
* **Average Latency:** $1.71 \text{ seconds}$
* **Average Tokens:** 386.5 total tokens ($175.5$ prompt + $211$ completion)
* **Behavior:** Highly efficient, lowest latency, ideal for low-complexity operational tasks.

#### 2. Tree of Thoughts (Course Sequencing & Path Ranking)

* **LLM Calls:** 9 calls per task
* **Average Latency:** $22.62 \text{ seconds}$
* **Branching Factor:** 6 generated branches, 2 pruned branches
* **Final Beam Size:** 2 optimal pathways retained
* **Behavior:** Deep reasoning with high coverage, ideal for multi-option trade-off analysis.

#### 3. LATS (Schedule Optimization with Environment Feedback)

* **LLM Calls:** 2 calls per task
* **Average Latency:** $4.39 \text{ seconds}$
* **Iterations Used:** 1 iteration
* **Best Reward Score:** Reached up to **0.933**
* **Behavior:** Environment-guided dynamic trajectory sampling, high accuracy for multi-constraint schedule optimization.

---

## How to run the full demo

```bash
cd memory
python reset_memory_tables.py
python run_kareem_story.py        # seeds a real semantic fact + resolves a real conflict

cd ../rag
python build_index.py             # (re)builds the Chroma index from policies/

cd ../agent
python run_demo.py                # runs one policy question + one memory question end-to-end
```

## Repository layout

- `mcp_server/`, `db/`, `client/` — existing system from the MCP Server Lab (reused, not duplicated)
- `memory/` — short-term buffer + scratchpad, episodic store, promote-or-drop router, consolidation with conflict resolution
- `context_eval/` — 4 context management strategies, long-context test suite, comparison table
- `policies/` — the RAG corpus, grounded in the actual `db/` schema (status, grade, role, certificate_code — no invented fields)
- `rag/` — chunking/ingestion, Chroma vector store, naive/hybrid/agentic RAG, Self-RAG verification
- `retrieval_eval/` — 12 domain-specific test questions, comparison script, debugging log
- `agent/` — integration layer: intent routing + the unified agent loop

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the repo root with:
```
ANTHROPIC_API_KEY=your_key_here
```
(Not required for `run_demo.py`'s db_tool/memory paths or for the
retrieval-only comparison script; required for live generation via
`rag/generate.py` and the LLM-based Self-RAG support check.)
