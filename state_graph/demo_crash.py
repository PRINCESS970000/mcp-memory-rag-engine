import sys
from pathlib import Path
import json
import uuid

# Add parent directory to sys.path for absolute imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_1_study_abroad import (
    run_or_resume_graph,
    set_external_signal,
)
from base import resolve_hitl_task, get_latest_hitl_task

# Generate a unique THREAD ID per execution to prevent previous state persistence errors
THREAD = f"demo_thread_omar_{uuid.uuid4().hex[:8]}"


def show(label, state):
    print(f"\n===== {label} =====")
    print("Current Status:", state.get("status"))
    print(json.dumps(state, indent=2, ensure_ascii=False))


# 1) Start the graph: execution should pause at "pending_external"
state = run_or_resume_graph(THREAD)
show("Run #1: (start -> pending_external)", state)
assert state["status"] == "pending_external"


# 2) Simulate external rejection for the first program (ETH Zurich)
set_external_signal(THREAD, 0, "rejected")


# 3) Resume execution and select the next available program
state = run_or_resume_graph(THREAD)
show("Run #2: resume after first rejection", state)
assert state["status"] == "pending_external"
assert state["rejected_programs"] == ["Exchange Program - ETH Zurich"]
assert state["student_name"] == "Omar Khaled"  # Preserved state without rebuilding


# 4) The new external provider (Siemens Munich) approves the request
set_external_signal(THREAD, 1, "approved")


# 5) Resume execution: pauses at the Human-In-The-Loop (HITL) gate for admin review
state = run_or_resume_graph(THREAD)
show("Run #3: resume -> HITL gate (pending admin review)", state)
assert state["status"] == "paused_for_hitl"

hitl_task = get_latest_hitl_task(THREAD)
print(f"\n[Admin Dashboard] HITL Task #{hitl_task['id']}: {hitl_task['reason']}")


# 6) Admin approves the HITL task
resolve_hitl_task(hitl_task["id"], "approved")


# 7) Resume execution until completion
state = run_or_resume_graph(THREAD)
show("Run #4: resume -> finalized", state)
assert state["status"] == "finalized"

print("\n Execution completed successfully! ")