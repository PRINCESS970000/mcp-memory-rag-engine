"""
state_graph/demo_crash_resume.py

Terminal 1: python demo_crash_resume.py start
Terminal 2: python demo_crash_resume.py resume
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import base
from graph_2_graduation import run_graduation_graph, run_or_resume_graph, GraphInternalState, GraduationState

THREAD_ID = "demo-graduation-thread"


async def start_and_crash():
    initial_state: GraphInternalState = {
        "application_id": 9999,
        "student_id": 1,
        "department": "cs_fundamentals",
        "thread_id": THREAD_ID,
        "current_state": GraduationState.APPLICATION_SUBMITTED.value,
        "total_corrections": 0,
        "max_corrections": 5,
        "policy_context": None,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }

    print(">>> Starting the first run...")
    await run_graduation_graph(
        THREAD_ID, start_node="academic_check", state=initial_state, _crash_after_node="academic_check"
    )


async def resume():
    saved_state = base.load_latest_checkpoint(THREAD_ID)
    if saved_state is None:
        print(">>> No checkpoint found -- run 'start' first.")
        return

    print(f">>> Last executed node = {saved_state.get('_last_node')}, current_state = {saved_state.get('current_state')}")
    print(">>> Resuming the run...")
    await run_or_resume_graph(THREAD_ID)
    print(">>> Finished without re-running node academic_check.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "resume"):
        print("استخدام: python demo_crash_resume.py [start|resume]")
        sys.exit(1)
    asyncio.run(start_and_crash() if sys.argv[1] == "start" else resume())