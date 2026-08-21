"""
state_graph/demo_ticket_failure.py

يثبت إن فشل فني حقيقي (MCP tool بيرجع status != success) بيتحول لـ
failure_ticket، والـ graph بيوقف، وبيكمل من نفس الـ node بعد ما "فريق
الدعم" يحل الـ ticket -- عن طريق نفس الطبقة الحقيقية اللي هيستخدمها
app.py في المنصة (platform/admin/data_access.py: resolve_ticket_and_resume)،
مش عن طريق تعديل يدوي في الداتابيز.

⚠️ ملاحظتين مهمتين:

1. resolve_ticket_and_resume بيحدد نوع الـ graph من بادئة الـ thread_id
   نفسه (شوفي _infer_graph_type_from_thread_id في data_access.py)، لأن
   جدول failure_tickets معندوش عمود graph_type. عشان كده THREAD_ID هنا
   لازم يبدأ بـ "graduation" بالظبط -- ده اتفاق فريق لازم الكل يلتزم بيه.

2. زي demo_hitl.py، resolve_ticket_and_resume بينادي asyncio.run() جواه،
   فلازم يتنادى من كود sync عادي مش من جوه async def شغالة أصلاً.

ملاحظة على النتيجة المتوقعة: بيانات الطالب 1 (Omar Khaled) في
cs_fundamentals عندها 6 ساعات مكتملة فقط مقابل 12 مطلوبة. يعني بعد حل
الـ ticket، academic_check هيتنادى فعليًا (مش mock) ويرجع clear=False
بشكل صحيح، فالـ graph هيكمل طبيعي في اللوب (missing_course ->
student_correction -> ...) لحد ما يوصل rejected بعد استنفاد
max_corrections. ده متوقع ومقبول -- المطلوب إثباته هو إن الـ ticket
اتحل والـ node اشتغل فعليًا من الداتابيز الحقيقية، مش إتخطاه.

تشغيل:
    python demo_ticket_failure.py
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import patch

STATE_GRAPH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = STATE_GRAPH_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "platform" / "admin"))

import graph_2_graduation as g2
from graph_2_graduation import run_graduation_graph, run_or_resume_graph, GraphInternalState, GraduationState
import data_access  # الطبقة الحقيقية اللي هتستخدمها المنصة

# لازم يبدأ بـ "graduation" عشان resolve_ticket_and_resume يقدر يوجّهه صح
THREAD_ID = "graduation-demo-ticket"


async def _crash_the_tool() -> int:
    initial_state: GraphInternalState = {
        "application_id": 7777,
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

    async def fake_failing_call(tool_name, **kwargs):
        if tool_name == "get_academic_status":
            return {"status": "error", "message": "MCP server timeout (محاكاة)"}
        raise RuntimeError(f"مفروض متتنادوش أداة تانية في الديمو ده: {tool_name}")

    print(">>> محاكاة فشل فني في get_academic_status...")
    with patch.object(g2, "call_mcp_tool", side_effect=fake_failing_call):
        state = await run_graduation_graph(THREAD_ID, start_node="academic_check", state=initial_state)

    assert state.get("pending_ticket_id") is not None, "❌ المفروض ticket يتعمل"
    print(f">>> ✅ الـ graph وقف بسبب ticket #{state['pending_ticket_id']} -- فشل فني حقيقي، مش قرار طالب.")
    return state["pending_ticket_id"]


async def _try_resume_before_fix():
    print(">>> محاولة استئناف *قبل* حل الـ ticket (المفروض يفضل واقف)...")
    state = await run_or_resume_graph(THREAD_ID)
    assert state.get("pending_ticket_id") is not None
    print(">>> ✅ لسه واقف زي المتوقع.")


def main():
    ticket_id = asyncio.run(_crash_the_tool())
    asyncio.run(_try_resume_before_fix())

    # هنا بالظبط اللي المفروض يحصل لما فريق الدعم يضغط "Resolve" من شاشة
    # الإدارة الحقيقية: نداء sync لـ data_access، وهو اللي بيتولى تحديث
    # حالة الـ ticket واستئناف الـ graph من نفس الـ node.
    print(f">>> [PLATFORM] فريق الدعم بيحل ticket #{ticket_id} من شاشة الإدارة...")
    result = data_access.resolve_ticket_and_resume(ticket_id)

    assert result["graph_type"] == "graduation", "❌ data_access وجّه الـ ticket لـ graph غلط"
    final_state = result["resulting_state"]

    print(">>> ✅ academic_check اتنفذ تاني فعليًا (مش اتخطى) ورجع نتيجة حقيقية من الداتابيز.")
    print(f">>> current_state النهائي = {final_state['current_state']}")
    print(f">>> عدد المحاولات = {final_state['total_corrections']}")


if __name__ == "__main__":
    main()