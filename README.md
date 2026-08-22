# Final Project — State Graphs, Human-in-the-Loop, and the Platform

This section covers the Final Project layer built on top of the existing
`mcp_server/`, `db/`, and the agents from the previous three labs
(MCP Server Lab, Memory & RAG Lab, Decomposition & Planning Lab).

## The three state-graph problems

| # | Graph | Owner | File |
|---|---|---|---|
| 1 | Study Abroad & Internship Placement Coordination | Person 1 | `state_graph/graph_1_study_abroad.py` |
| 2 | Graduation Clearance | Person 2 | `state_graph/graph_2_graduation.py` |
| 3 | Internship Readiness & Application | Person 3 (Eman) | `state_graph/graph_3_internship.py` |

None of the three is a re-skin of the scheduling problem from the
Decomposition & Planning Lab or the retrieval problem from the Memory &
RAG Lab — each is a genuinely new agent scope with its own real wait, real
external branch, and real failure mode:

### Graph 3 — Internship Readiness & Application (owned by Eman)

- **Why a state graph:** a student's path from "interested in a role" to
  "hired" spans a real course-completion wait (`course_in_progress`, can
  be weeks) and a real company-response wait after submission
  (`submitted_awaiting_company`) — neither is resolvable by a retry.
- **Real branch outside the model's control:** whether the company
  accepts or rejects is an external decision, not something the graph
  computes.
- **Real failure mode:** an unrecognized `role_title` or a broken MCP
  call opens a `failure_ticket`, distinct from the HITL path.
- **Two of the four additions used, and why:**
  - *RAG* (`node_analyze_skill_gap`) — pulls the role's real required
    skills and BrightPeak's course catalog instead of letting the model
    guess what a role needs.
  - *Task decomposition* (`node_check_readiness`) — breaks "is this
    student ready to apply?" into four checked steps (`skills`, `cv`,
    `courses`, `documents`) instead of one opaque yes/no.
- **HITL condition:** submitting the application to a real external
  company is irreversible, so `node_hitl_submit_gate` always pauses for
  Admin/advisor sign-off before `node_submit_application` runs —
  regardless of how confident the readiness check is.
- **Ticket path:** any failed MCP call (e.g. `get_role_requirements` on a
  role that doesn't exist) opens a ticket via
  `state_graph/tickets/dedupe.py`, separate from the HITL table.
- **Proof of checkpointing (crash-and-resume):** `state_graph/test_internship_flows.py`
  starts a run, kills the process with `os._exit(1)` right after
  `analyze_skill_gap`, restarts in a new process, and shows the run
  resuming at `check_readiness` without re-calling `analyze_skill_gap` —
  the same three flows (HITL, ticket, crash-resume) are proven end to end
  through the **same functions the platform's admin UI calls**
  (`platform/admin/data_access.py`), not a separate test-only code path.

### Graph 2 — Graduation Clearance (owned by teammate)

- **Why a state graph:** clearance depends on academic status, an
  outstanding financial balance, a library debt, and required documents —
  each can be missing and each is fixed by the *student*, not the agent,
  on their own schedule.
- **Real branch:** whether each check passes depends on live data
  (`get_academic_status`, `get_financial_status`, `get_library_status`,
  `get_required_documents`), not a model guess.
- **Two additions used:** RAG (graduation policy retrieval) + constrained
  ReAct (each check node may only call its one designated MCP tool).
- **HITL condition:** `node_admin_approval` — final graduation sign-off
  is irreversible and always requires Admin approval once every
  automated check has cleared.
- **Correction made this project:** the four correction loops
  (`student_correction`, `financial_hold`, `library_issue`,
  `student_upload`) originally routed straight back to their check node
  *inside the same synchronous call*, up to `max_corrections` times in
  one shot — meaning the "wait" never actually paused across turns, the
  opposite of what a state graph is supposed to prove. Fixed so each of
  the four now returns `None` (a genuine pause, checkpointed), and
  `run_or_resume_graph` re-checks the underlying condition only when
  something calls resume again — so `total_corrections` now reflects real
  separate attempts over time, not iterations inside one function call.

### Graph 1 — Study Abroad & Internship Placement Coordination (owned by teammate)

- **Why a state graph:** a nomination depends on a host university or
  company's reply and an interview schedule, both external and
  unpredictable in timing.
- **Real failure mode:** a rejection or an expired application window
  re-routes the student to a second-choice option without losing the
  completed application data already collected.
- **Two additions used:** LATS (ranks candidate placements against the
  student's academic/financial record) + constrained ReAct (submits only
  through the whitelisted MCP tools).
- **HITL condition:** final sign-off on the nomination letter or any
  financial support requires direct Admin approval.

## Shared infrastructure (not duplicated per graph)

- **Checkpointing** — `state_graph/base.py`: `checkpoints`, `hitl_tasks`,
  and `failure_tickets` tables, shared by all three graphs against the
  same `db/brightpeak.db` used by the rest of the system (not a separate
  database).
- **Ticket system** — `state_graph/tickets/`:
  - `dedupe.py` — prevents opening a duplicate ticket for the same
    thread/node while one is already open.
  - `resolve.py` — the single resolution path used by the platform.
  - `stagnation_check.py` — a *scheduled* check (not a manual one) that
    opens a ticket when a thread has been sitting in a real external-wait
    state longer than that state's threshold (e.g.
    `submitted_awaiting_company` > 30 minutes for the demo,
    `course_in_progress` > 2 hours) — this is what proves a stall is
    *detected*, not manually inserted for the demo.
- **Platform** — `platform/admin/` (tool management, RAG document
  management, HITL/ticket resolution) and `platform/user/` (agent
  switcher + chat), both wired against the live `mcp_server/` and the
  same `db/brightpeak.db`.

## Corrections made to the existing system during this project

1. **`state_graph/base.py`** — `DB_PATH` resolved one directory too high
   (`"..", ".."` instead of `".."`), so every checkpoint, HITL task, and
   ticket was silently being written to a *separate* SQLite file outside
   the repository, disconnected from the real `db/brightpeak.db`. Fixed
   to the correct single-`".."` path.
2. **`platform/admin/data_access.py`** — `GRAPH_REGISTRY` only registered
   the graduation graph; resolving a HITL task or ticket for the
   internship or study-abroad graphs through the platform would have
   raised an error. Registered both, and wrapped `graph_1_study_abroad`'s
   `run_or_resume_graph` (a plain `def`) in a small `async` adapter,
   since every call site in `data_access.py` does `await run_or_resume_fn(...)`.
3. **`state_graph/graph_2_graduation.py`** — see "Graph 2" above: four
   correction loops were resolving synchronously in one call instead of
   genuinely pausing across turns.
4. **`state_graph/tickets/stagnation_check.py`** — the stagnation rule
   for graph 2 referenced a state name (`awaiting_sponsor_verification`)
   left over from before the graph was renamed from "scholarship" to
   "graduation", so it matched nothing. Replaced with the graph's actual
   wait states.
5. **`db/graduation_schema.sql`** — existed but was never applied
   automatically by `db/init_db.py`, so a fresh clone would crash the
   moment graph 2 tried to submit an application. Documented as a
   required setup step below.
6. **`mcp_server/server.py` / tool registration** — `scholarship_tools.py`
   and the earlier internship tool file used to do `from server import
   mcp, get_db_connection` at import time, before `server.py` had
   finished defining `get_db_connection` — a circular import that broke
   `python server.py` standalone. Fixed by switching to the
   `register(mcp, get_db_connection)` pattern used by
   `graduation_tools.py` and `internship_tools.py`.
7. **Memory & RAG Lab** — see the "Agent integration" section above for
   the three bugs already fixed there (router shadowing, Self-RAG
   relevance floor, intent-routing priority).

## Setup (updated)

```bash
pip install -r requirements.txt
cd db
python init_db.py
python -c "import sqlite3; conn = sqlite3.connect('brightpeak.db'); conn.executescript(open('graduation_schema.sql', encoding='utf-8').read()); conn.commit()"
cd ..
```

## Demo evidence

- `state_graph/test_internship_flows.py` — HITL, ticket, and
  crash-and-resume for Graph 3, all through the real platform functions.
- `state_graph/test_hitl_and_ticket.py` — HITL and ticket for Graph 2.
- [add: recording/transcript for Graph 1's HITL + crash-resume]
- [add: screen recording of the admin and user platform surfaces]
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

### Planning Agent (`agent/planning_agent.py`, `planning/`)

A separate agent from the memory/RAG agent above, owning a different real
problem: a student asking for a personalized course path to reach a target
job role, which has to respect real prerequisites, budget, weekly-hour
capacity, and a deadline. `intent_router.route_intent()` sends these
requests (checked before POLICY/DB_TOOL, since phrases like "path to
become a Data Scientist" can otherwise match DB_TOOL's "course" keyword)
to `agent/loop.py`'s `_handle_planning_question()`, which calls
`planning_agent.run_learning_path_request()`. Both reuse the same
`mcp_server/` and `db/` as every other agent — see
`planning/README.md` for the full decomposition, planning-algorithm,
self-correction, and grounding writeup, and `planning_eval/README.md` for
the comparison table and evidence.

## 📑 Overview & Architecture

The planning subsystem receives task specifications and uses a **Routing Engine** to assign each subtask to the most suitable search and planning strategy:

1. **Plan-and-Solve (PS):** Zero-shot / single-pass decomposition for deterministic parsing, formatting, and mathematical constraint calculations.
2. **Tree of Thoughts (ToT):** Tree-based systematic search using beam-search evaluation and branch pruning for sequencing and ranking decisions under time/budget constraints.
3. **Language Agent Tree Search (LATS):** Monte Carlo Tree Search (MCTS) enhanced with environment trajectory feedback and value scoring for schedule optimization.

---

##  Summary of Execution Traces & Performance Metrics

Below is the summary of evaluation metrics collected across 9 representative test executions generated via `scripts/manual_router_check.py` (formerly `tests/test_runner.py` — moved out of `tests/` since it calls the real Mistral API and isn't an offline unit test) using **Mistral AI**:

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

#### 4. Self-Refine vs. Reflexion (`salma_tight_constraints` case — student with the tightest simultaneous budget/hours/deadline in the seed data)

| Method | Grounded score | Attempts | Behavior |
| --- | --- | --- | --- |
| Self-Refine (single pass) | 0.17 (1/6 checks) | 1 draft + 1 revision | Fixed nothing meaningfully: still over budget ($1000 vs $500), still 30 weekly hours vs. 8 available, still 2 unmet prerequisites, still misses the deadline. One revision (dropping the last course) can't fix constraints that interact this much. |
| Reflexion (multi-trial) | 0.50 (3/6 checks) | 3 trials, 6 LLM calls | Each trial's grounded feedback becomes the next trial's explicit strategy ("I'll prioritize prerequisites first... space out high-hour courses...") — genuinely reasons about *why* it failed, not just retries blindly. Still doesn't fully succeed (this catalog's overlapping dates make full success for this student's 8hr/week cap genuinely hard), but reaches 3x Self-Refine's score. |

Full trace: [`artifacts/self_refine_vs_reflexion_trace.json`](artifacts/self_refine_vs_reflexion_trace.json).
Reflexion is what the agent ships with for the "propose a complete path" sub-task; Self-Refine is reserved for the cheap, low-interaction sub-task of writing the student-facing explanation (see `planning/algorithms/self_refine.py`'s module docstring).

#### 5. Decomposition-first vs. dynamic decomposition

| Case | Method | Result |
| --- | --- | --- |
| `omar_stable_plan` (roomy budget/hours/deadline, no known complications) | decomposition-first | 8-task plan generated in one shot, 16.6s. Cheaper and just as good — nothing in this student's real data forces a mid-plan change. |
| `omar_stable_plan` | dynamic | 4 reactive steps, 9.9s. No divergence from decomposition-first — confirms the "roomy, stable" case doesn't need reactive planning. |
| `kareem_dropped_course` (real `enrollments` row: course_id=1, grade=45.0, status=DROPPED) | decomposition-first | Generic 8-task plan (`verify prerequisites`, `select_courses`) — never specifically addresses the dropped course. |
| `kareem_dropped_course` | dynamic | After observing the real DROPPED status in step 1, step 4's course search surfaces course_id=1 (the dropped course) as a candidate again — the plan reacts to the failure decomposition-first would have silently ignored. |

Full trace: [`artifacts/decomposition_comparison_trace.json`](artifacts/decomposition_comparison_trace.json).
Dynamic decomposition ships as the default for the top-level path request; decomposition-first is kept for the fully mechanical sub-tasks with no real branching (e.g. `t2`'s role-requirement lookup).

#### 6. LATS grounded vs. ungrounded `Environment` (`hoda_many_valid_orderings` case)

| Environment | LATS's own belief | Real grounded check of the same output |
| --- | --- | --- |
| Ungrounded (`RandomEnvironment`, the toolkit's original randomized default) | `success: true`, score 0.84, 1 iteration, 2 LLM calls | `success: false`, **score 0.5** — real budget exceeded by $930, weekly hours exceeded 2–3x over (up to 38 vs. the 15hr limit), and a real prerequisite/schedule violation (course 3 starts before its prerequisite, course 1, ends) |
| Grounded (`Environment`, real MCP/DB checks) | `success: false`, score 0.83, 2 iterations, 10 LLM calls | Same — the score IS the real check, so there's no gap between belief and reality |

Full trace: [`artifacts/lats_grounded_vs_ungrounded_trace.json`](artifacts/lats_grounded_vs_ungrounded_trace.json).
This is the case the grounding requirement exists for: the ungrounded run finished faster and *believed* it had succeeded, but its own proposal would have double-booked the student and blown the budget by 93%. The grounded run costs 5x the LLM calls and never claims success on a genuinely infeasible catalog, which is the correct behavior. LATS ships wired to the real `Environment` for exactly this reason.

**Full demo transcript combining all four comparisons above, plus a real Self-Refine draft→critique→revision on its actual designed sub-task:** [`planning_eval/demo_transcript.md`](planning_eval/demo_transcript.md).

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
python -c "
from short_term import ShortTermMemory
from loop import handle_message
stm = ShortTermMemory(session_id='demo-planning-session', student_id=4)
print(handle_message(stm, 4, 'Help me plan a learning path to become a Data Analyst'))
"                                  # routes to the Planning Agent instead

cd ..
python -m planning.cli "Build my course path to become a Data Analyst" --mode dynamic --student-id 4
                                   # or --mode dag -- see planning/cli.py --help
python -m planning_eval.run_reflexion_vs_selfrefine
                                   # Self-Refine vs Reflexion comparison, saves artifacts/ trace
```

## Repository layout

- `mcp_server/`, `db/`, `client/` — existing system from the MCP Server Lab (reused, not duplicated)
- `memory/` — short-term buffer + scratchpad, episodic store, promote-or-drop router, consolidation with conflict resolution
- `context_eval/` — 4 context management strategies, long-context test suite, comparison table
- `policies/` — the RAG corpus, grounded in the actual `db/` schema (status, grade, role, certificate_code — no invented fields)
- `rag/` — chunking/ingestion, Chroma vector store, naive/hybrid/agentic RAG, Self-RAG verification
- `retrieval_eval/` — 12 domain-specific test questions, comparison script, debugging log
- `agent/` — integration layer: intent routing + the unified agent loop (memory/RAG agent + Planning Agent)
- `planning/` — the Planning Agent's implementation: decomposition (both methods), Plan-and-Solve/Tree of Thoughts/LATS, Self-Refine/Reflexion, the grounded `Environment`. Forked from [AmrSheta22/task_decomposition_and_planning](https://github.com/AmrSheta22/task_decomposition_and_planning) and adapted to this project's real MCP tools and database.
- `planning_eval/` — the Planning Agent's fixed test suite, comparison scripts, and evidence traces backing the comparison table below
- `artifacts/` — JSON run traces from both agents (plans, node outputs, critic feedback, episodic memories, MCTS visits, branch reflections)

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

Add to the same root `.env` file:
```
MISTRAL_API_KEY=your_key_here
```
(Used by `planning/cli.py` and `agent/planning_agent.py` for every
algorithm in the Planning Agent — decomposition, Plan-and-Solve, Tree of
Thoughts, LATS, Self-Refine, and Reflexion — all through one consistent
`langchain-mistralai` client, so the whole planning subsystem needs only
this one key, not a second provider.)