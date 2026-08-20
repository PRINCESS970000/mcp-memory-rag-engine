import sys
import asyncio
from pathlib import Path
 
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
 
import base
from graph_2_scholarship import (
    run_scholarship_graph,
    run_or_resume_graph,
    GraphInternalState,
    ScholarshipState,
)
 
THREAD_ID = "demo-crash-resume-thread"
 
 
async def start_and_crash():
    initial_state: GraphInternalState = {
        "application_id": 9999,
        "student_id": 1,
        "thread_id": THREAD_ID,
        "requested_amount": 1000.0,
        "sponsor_name": "Demo Sponsor",
        "approved_amount": None,
        "current_state": ScholarshipState.APPLICATION_SUBMITTED.value,
        "appeal_count": 0,
        "max_appeals": 2,
        "installments_paid": 0,
        "total_installments": 3,
        "policy_context": None,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }
 
    print(">>> بدء الـ run الأول...")
    await run_scholarship_graph(
        THREAD_ID,
        start_node="check_eligibility",
        state=initial_state,
        _crash_after_node="check_eligibility",
    )
    # مش هيوصل هنا خالص -- os._exit بتقفل العملية فورًا
 
 
async def resume():
    saved_state = base.load_latest_checkpoint(THREAD_ID)
    if saved_state is None:
        print(">>> مفيش checkpoint محفوظ -- شغلي 'start' الأول.")
        return
 
    print("checkpoint ")
    print(f"    آخر node اتنفذ = {saved_state.get('_last_node')}")
    print(f"    current_state = {saved_state.get('current_state')}")
 
    print("run_or_resume_graph...") #>>> إكمال الـ run بنفس الدالة الموحدة run_or_resume_graph...
    await run_or_resume_graph(THREAD_ID)
 
    print("node check_eligibility ")#>>> خلص الـ run من غير ما node check_eligibility يتنفذ تاني.
 
 
if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "resume"):
        print("استخدام: python demo_crash_resume.py [start|resume]")
        sys.exit(1)
 
    if sys.argv[1] == "start":
        asyncio.run(start_and_crash())
    else:
        asyncio.run(resume())