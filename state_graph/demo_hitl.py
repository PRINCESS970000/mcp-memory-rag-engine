"""
state_graph/demo_hitl.py

يثبت إن الـ graph بيوصل لـ admin_approval ويوقف فعليًا (مش mock)، وإن
الاستئناف بيحصل فقط بعد ما "الأدمن" يوافق -- عن طريق نفس الطبقة الحقيقية
اللي هيستخدمها app.py في الـ platform (platform/admin/data_access.py)،
مش عن طريق نداء مباشر لـ base.resolve_hitl_task.

⚠️ ملاحظة تقنية مهمة: resolve_hitl_and_resume بينادي asyncio.run() جواه.
عشان كده استدعاؤه لازم يكون من كود sync عادي (زي ما هيحصل فعليًا من جوه
Flask endpoint)، مش من جوه async def شغالة أصلاً تحت asyncio.run() --
وإلا هترمي RuntimeError. فالسكريبت ده متبني عمدًا كـ sync في الأعلى،
وبينادي asyncio.run() بس للأجزاء اللي بتلمس الـ graph مباشرة.

تشغيل:
    python demo_hitl.py
"""

import sys
import asyncio
from pathlib import Path

# state_graph/ نفسه -- نفس بنية demo_crash_resume.py
STATE_GRAPH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = STATE_GRAPH_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "platform" / "admin"))

from graph_2_graduation import run_graduation_graph, run_or_resume_graph, GraphInternalState, GraduationState
import data_access  # الطبقة الحقيقية اللي هتستخدمها المنصة

# لازم يبدأ بـ "graduation" اتساقًا مع الاتفاق (شوفي التعليق في data_access.py)
THREAD_ID = "graduation-demo-hitl"


async def _reach_admin_approval() -> int:
    """
    بنبدأ مباشرة عند admin_approval عشان نختبر الـ HITL بمعزل عن الفحوصات
    الأربعة (اللي محتاجة بيانات طالب حقيقية). الهدف هنا إثبات سلوك
    node_admin_approval + الوقوف الفعلي، مش إعادة اختبار الفحوصات.
    """
    initial_state: GraphInternalState = {
        "application_id": 8888,
        "student_id": 1,
        "department": "cs_fundamentals",
        "thread_id": THREAD_ID,
        "current_state": GraduationState.DOCUMENT_OK.value,
        "total_corrections": 0,
        "max_corrections": 5,
        "policy_context": "دفعة اختبار HITL",
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }

    print(">>> بدء الـ run لحد admin_approval...")
    state = await run_graduation_graph(THREAD_ID, start_node="admin_approval", state=initial_state)

    assert state.get("pending_hitl_id") is not None, "❌ الـ graph المفروض يوقف عند HITL"
    assert state["current_state"] == GraduationState.AWAITING_ADMIN_APPROVAL.value

    print(f">>> ✅ الـ graph واقف فعليًا عند HITL task #{state['pending_hitl_id']}")
    return state["pending_hitl_id"]


async def _try_resume_before_decision():
    """محاولة استئناف قبل ما الأدمن يقرر -- المفروض يفضل واقف."""
    print(">>> محاولة استئناف *قبل* قرار الأدمن (المفروض يفضل واقف)...")
    state = await run_or_resume_graph(THREAD_ID)
    assert state["current_state"] == GraduationState.AWAITING_ADMIN_APPROVAL.value
    print(">>> ✅ لسه واقف زي المتوقع.")


def main():
    # الأجزاء اللي بتلمس الـ graph مباشرة -- async
    hitl_id = asyncio.run(_reach_admin_approval())
    asyncio.run(_try_resume_before_decision())

    # هنا بالظبط اللي المفروض يحصل لما الأدمن يضغط "Approve" من شاشة
    # الإدارة الحقيقية: نداء sync لـ data_access، وهو اللي بيتولى
    # الـ resolve + resume كلها من غير ما إحنا نلمس base.py أو
    # run_or_resume_graph تاني بإيدنا.
    print(f">>> [PLATFORM] الأدمن بيوافق من شاشة الإدارة على task #{hitl_id}...")
    result = data_access.resolve_hitl_and_resume(hitl_id, approved=True)

    assert result["graph_type"] == "graduation", "❌ data_access وجّه الـ task لـ graph غلط"
    final_state = result["resulting_state"]
    assert final_state["current_state"] == GraduationState.RESOLVED.value, "❌ المفروض يوصل approved/resolved"

    print(">>> ✅ الـ graph كمل واعتمد التخرج -- عن طريق data_access.py الحقيقي، مش نداء مباشر لـ base.py.")
    print(f">>> current_state النهائي = {final_state['current_state']}")


if __name__ == "__main__":
    main()