# memory/

(placeholder — work in progress for the Memory & RAG lab)
## Memory System — Student Re-Enrollment Exceptions

### The problem
Front-desk agents at BrightPeak Academy field repeat calls from students who
were dropped from a course and are trying to get back in. Each call, the
agent has no memory of what was already decided — so a student who was
previously denied re-enrollment gets asked to re-explain their situation
from scratch, and worse: a student whose exception was later approved
risks being told "no" again, because the agent has no record that the
decision changed.

This is not a hypothetical: BrightPeak's `enrollments` table already shows
students with `DROPPED` status (e.g. student_id 7, CS101, grade 45). Any of
these students may call back multiple times as their situation evolves
(new documentation, appeals, policy exceptions). Forgetting — or worse,
surfacing a stale decision — has a direct, real cost to the student.

### How each memory concern shows up

| Concern | Implementation |
|---|---|
| **Short-term buffer** | Reuses the existing `messages` table / `store_message()` / `get_chat_history()` in `mcp_server/server.py` — not duplicated. |
| **Scratchpad** | `memory/short_term.py` — a `Scratchpad` class holding `student_id`, `current_topic`, `next_step`, kept fully separate from the buffer so pruning old messages never erases it. Verified: after 25 messages overflow a 20-message buffer, the scratchpad is untouched. |
| **Promote-or-drop routing** | `memory/router.py` — routes an aging buffer message to episodic memory only if it's a `user` message AND contains a relevant keyword (`drop`, `re-enrollment`, `exception`, `appeal`, etc). Every decision (forget or promote) is logged with its reasoning to `router_decisions.log`. Never writes to semantic memory directly. |
| **Episodic store** | `memory/episodic_store.py` — SQLite table `episodic_events` (in the existing `brightpeak.db`) storing raw events like "Admin decision: DENIED — must wait one semester." |
| **Semantic consolidation** | `memory/consolidation.py` — a separate, periodic pass (`consolidate_student()`) over episodic events. Detects the latest decision, compares it against the current semantic fact, and resolves conflicts: the old fact is never deleted, only marked `is_current=0` with a `superseded_by` link and `valid_until` timestamp; a new versioned fact takes over. |
| **Self-RAG-style verification** | `memory/self_check.py` — before a recalled semantic fact reaches the agent, `check_relevance()` verifies real keyword overlap between the question and the fact. A fact about "CS101 re-enrollment" is correctly rejected when asked about an unrelated course. |

### The real conflict, demonstrated

Story used for testing (`memory/run_kareem_story.py`):

1. Kareem requests re-enrollment in CS101 after a drop → DENIED
2. Kareem asks again → DENIED (same policy)
3. Kareem submits medical documentation → APPROVED
4. Admin later reverses the decision → DENIED

Running consolidation twice produces:
Step 1: {'status': 'created', 'fact_text': 'CS101 re-enrollment: APPROVED ...'}
Step 2: {'status': 'conflict_resolved',
'old_fact': 'CS101 re-enrollment: APPROVED ...',
'new_fact': 'CS101 re-enrollment: DENIED ...',
'superseded_fact_id': 1}


The old APPROVED fact is preserved (`is_current=0`, `superseded_by=2`), not
overwritten — a grader can trace the full decision history.

### Files

- `memory/short_term.py` — rolling buffer wrapper + scratchpad
- `memory/episodic_store.py` — episodic + semantic table schema, event logging
- `memory/router.py` — promote-or-drop decision logic + logging
- `memory/consolidation.py` — periodic consolidation + conflict resolution
- `memory/self_check.py` — Self-RAG-style relevance verification
- `memory/reset_memory_tables.py` — testing utility, clears memory tables only
- `memory/run_kareem_story.py` — end-to-end demo script for this concern

### How to run the demo

```powershell
cd memory
python reset_memory_tables.py
python run_kareem_story.py
python self_check.py
```

