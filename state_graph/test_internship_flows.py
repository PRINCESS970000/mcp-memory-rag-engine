"""
state_graph/test_internship_flows.py

نفس فكرة test_hitl_and_ticket.py بالظبط، بس لـ graph_3_internship، وبيغطي
تلات حاجات:
1) HITL: طالب جاهز فعليًا (بيانات حقيقية) -> hitl_submit_gate بيوقف ->
   بيتحل عن طريق نفس دالة المنصة (platform/admin/data_access.py) -> الـ
   run بيكمل ويقدّم فعليًا ويستنى رد الشركة.
2) Ticket: role_title مش موجود أصلًا -> get_role_requirements بيرجع
   status=error حقيقي من MCP -> ticket بيتفتح -> بيتحل عن طريق نفس دالة
   المنصة -> الـ run بيكمل من نفس النقطة.
3) Crash-resume: تشغيل حقيقي بعملية منفصلة، os._exit بعد analyze_skill_gap،
   وتشغيل تاني بيثبت إن الـ run استكمل من الـ checkpoint مش من الأول.

تشغيل (من جوه state_graph/):
    python test_internship_flows.py hitl
    python test_internship_flows.py ticket
    python test_internship_flows.py crash_start
    python test_internship_flows.py crash_resume
"""

import sys
import os
import sqlite3
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform" / "admin"))

import base
import graph_3_internship as g3
import data_access


DB_PATH = base.DB_PATH


def ensure_ready_fixture(student_id: int = 1, role_title: str = "Software Engineer"):
    """
    بيضيف الكورس الناقص لدور Software Engineer عشان الطالب 1 يبقى جاهز
    فعليًا (مش محاكاة) لاختبار الـ HITL flow. آمن يتنفذ أكتر من مرة.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM enrollments WHERE student_id = ? AND course_id = 4", (student_id,)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO enrollments (student_id, course_id, grade, status) VALUES (?, 4, 90.0, 'COMPLETED')",
            (student_id,),
        )
        conn.commit()
    conn.close()


async def test_hitl_flow():
    ensure_ready_fixture()
    student_id, role_title = 1, "Software Engineer"

    print("=== STEP 1: تشغيل الـ graph من البداية على طالب جاهز فعليًا ===")
    state = await g3.start_new_application(student_id, role_title)
    print(f"current_state = {state['current_state']}, pending_hitl_id = {state.get('pending_hitl_id')}")
    assert state["current_state"] == g3.InternshipState.AWAITING_HITL_SUBMIT.value
    assert state["pending_hitl_id"] is not None, "HITL didn't actually pause!"

    print("\n=== STEP 2: الأدمن بيوافق عن طريق نفس دالة المنصة ===")
    resolution = await data_access.resolve_hitl_and_resume(state["pending_hitl_id"], approved=True)
    result_state = resolution["resulting_state"]
    print(f"graph_type استُنتج تلقائيًا = {resolution['graph_type']}")
    print(f"current_state بعد الموافقة = {result_state['current_state']}")
    assert resolution["graph_type"] == "internship"
    assert result_state["current_state"] == g3.InternshipState.SUBMITTED_AWAITING_COMPANY.value

    print("\n=== STEP 3: الشركة بترد فعليًا (webhook محاكى) ===")
    g3.set_external_signal(result_state["thread_id"], "company_response", "accepted")
    final_state = await g3.run_or_resume_graph(result_state["thread_id"])
    print(f"current_state النهائي = {final_state['current_state']}")
    assert final_state["current_state"] == g3.InternshipState.RESOLVED.value

    print("\n>>> HITL FLOW (INTERNSHIP) PROVEN END TO END <<<")


async def test_ticket_flow():
    student_id, bad_role_title = 1, "role-does-not-exist-in-job_roles"

    print("=== STEP 1: تشغيل الـ graph بدور مش موجود -> فشل MCP حقيقي ===")
    state = await g3.start_new_application(student_id, bad_role_title)
    print(f"pending_ticket_id = {state.get('pending_ticket_id')}")
    assert state["pending_ticket_id"] is not None, "Ticket didn't actually open!"

    print("\n=== STEP 2: الأدمن بيحل الـ ticket عن طريق نفس دالة المنصة ===")
    resolution = await data_access.resolve_ticket_and_resume(state["pending_ticket_id"])
    print(f"graph_type استُنتج تلقائيًا = {resolution['graph_type']}")
    print(f"_last_node بعد الاستكمال = {resolution['resulting_state'].get('_last_node')}")
    assert resolution["graph_type"] == "internship"

    print("\n>>> TICKET FLOW (INTERNSHIP) PROVEN END TO END <<<")
    print(">>> ملحوظة: هيفشل تاني بنفس السبب لأن role_title لسه مش موجود --")
    print(">>> ده متوقع، البيانات الأساسية لسه محتاجة تصليح حقيقي مش بس قفل التذكرة.")


async def crash_start():
    ensure_ready_fixture()
    student_id, role_title = 1, "Software Engineer"
    thread_id = f"internship-{student_id}-{role_title}"

    with open("demo_internship_thread.txt", "w") as f:
        f.write(thread_id)

    state: g3.GraphInternalState = {
        "application_id": None,
        "student_id": student_id,
        "thread_id": thread_id,
        "target_role_title": role_title,
        "missing_skills": None,
        "recommended_courses": None,
        "readiness_steps": None,
        "policy_context": None,
        "current_state": g3.InternshipState.STARTED.value,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }

    print(">>> بدء الـ run الأول (هيقفل العملية فجأة بعد analyze_skill_gap)...")
    await g3.run_internship_graph(
        thread_id, start_node="analyze_skill_gap", state=state,
        _crash_after_node="analyze_skill_gap",
    )
    # مش هيوصل هنا -- os._exit بتقفل العملية فورًا


async def crash_resume():
    with open("demo_internship_thread.txt") as f:
        thread_id = f.read().strip()

    saved_state = base.load_latest_checkpoint(thread_id)
    print(">>> checkpoint المحفوظ:")
    print(f"    آخر node اتنفذ = {saved_state.get('_last_node')}")
    print(f"    current_state  = {saved_state.get('current_state')}")
    print(f"    policy_context معبّى؟ = {bool(saved_state.get('policy_context') is not None)}")

    state = await g3.run_or_resume_graph(thread_id)
    print(">>> بعد الاستكمال:", state.get("current_state"))


if __name__ == "__main__":
    valid = ("hitl", "ticket", "crash_start", "crash_resume")
    if len(sys.argv) < 2 or sys.argv[1] not in valid:
        print(f"Usage: python test_internship_flows.py [{'|'.join(valid)}]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "hitl":
        asyncio.run(test_hitl_flow())
    elif cmd == "ticket":
        asyncio.run(test_ticket_flow())
    elif cmd == "crash_start":
        asyncio.run(crash_start())
    elif cmd == "crash_resume":
        asyncio.run(crash_resume())