"""
state_graph/graph_3_internship.py

Graph #3: Internship Readiness & Application Graph

External waits (real, not simulated in-process):
  1) course completion  -> COURSE_IN_PROGRESS
  2) company response after actual submission -> SUBMITTED_AWAITING_COMPANY

Irreversible action requiring HITL: the actual submission to the external
company always needs Admin/advisor sign-off before sending, regardless of
model confidence -> hitl_submit_gate.

Reuses existing shared MCP tools instead of duplicating them:
  get_role_requirements   (already defined in mcp_server/server.py)
  check_prerequisites     (already defined in mcp_server/server.py)
Only 3 new tools were added, in mcp_server/internship_tools.py:
  check_internship_readiness, submit_internship_application,
  update_internship_application_state (renamed to avoid clashing with
  scholarship_tools.py's update_application_state on the same MCP server).
"""

import os
from typing import TypedDict, Optional
from enum import Enum

from state_graph.base import (
    get_db_connection,
    save_checkpoint,
    load_latest_checkpoint,
    create_hitl_task,
    create_failure_ticket,
)
from state_graph.mcp_client_internship import call_mcp_tool
from state_graph.rag_client_internship import retrieve_internship_policy


# ---------------------------------------------------------------------------
# 1) الحالات والـ state
# ---------------------------------------------------------------------------

class InternshipState(str, Enum):
    STARTED = "started"
    SKILL_GAP_ANALYZED = "skill_gap_analyzed"
    COURSE_IN_PROGRESS = "course_in_progress"
    READINESS_CHECKED = "readiness_checked"
    AWAITING_HITL_SUBMIT = "awaiting_hitl_submit"
    SUBMITTED_AWAITING_COMPANY = "submitted_awaiting_company"
    COMPANY_ACCEPTED = "company_accepted"
    COMPANY_REJECTED = "company_rejected"
    RESOLVED = "resolved"


class GraphInternalState(TypedDict):
    application_id: Optional[int]
    student_id: int
    thread_id: str

    target_role_title: str
    missing_skills: Optional[list]
    recommended_courses: Optional[list]

    readiness_steps: Optional[dict]
    policy_context: Optional[str]

    current_state: str

    pending_hitl_id: Optional[int]
    pending_ticket_id: Optional[int]

    _last_node: Optional[str]


# ---------------------------------------------------------------------------
# 2) جداول/دوال خاصة بالانتظار الخارجي (domain-specific -- زي graph_1)
# ---------------------------------------------------------------------------

def init_domain_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS internship_external_signals (
            thread_id TEXT,
            signal_type TEXT,   -- 'course_completion' | 'company_response'
            signal TEXT,        -- 'completed' | 'accepted' | 'rejected' | NULL
            PRIMARY KEY (thread_id, signal_type)
        )
    """)
    conn.commit()
    conn.close()


def set_external_signal(thread_id: str, signal_type: str, signal: str):
    """بتتنادى من webhook حقيقي أو سكريبت محاكاة عشان تسجل رد خارجي فعلي."""
    init_domain_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO internship_external_signals (thread_id, signal_type, signal)
        VALUES (?, ?, ?)
    """, (thread_id, signal_type, signal))
    conn.commit()
    conn.close()


def get_external_signal(thread_id: str, signal_type: str) -> Optional[str]:
    init_domain_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT signal FROM internship_external_signals
        WHERE thread_id = ? AND signal_type = ?
    """, (thread_id, signal_type))
    row = cursor.fetchone()
    conn.close()
    return row["signal"] if row else None


# ---------------------------------------------------------------------------
# 3) الـ Nodes -- كل واحد بيرجع partial update بس
# ---------------------------------------------------------------------------

async def node_analyze_skill_gap(state: GraphInternalState) -> dict:
    """RAG: بيسحب من كتالوج كورسات Brightpeak + متطلبات الدور الفعلية."""
    print(">>> [RUNNING analyze_skill_gap]")

    result = await call_mcp_tool("get_role_requirements", role_title=state["target_role_title"])
    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", "unknown MCP error")}

    required_skills = result.get("data", {}).get("required_skills", [])

    policy_text = retrieve_internship_policy(query=f"متطلبات دور {state['target_role_title']}")

    return {
        "current_state": InternshipState.SKILL_GAP_ANALYZED.value,
        "missing_skills": required_skills,  # هيتظبط بدقة في node_check_readiness
        "policy_context": policy_text,
    }


async def node_check_readiness(state: GraphInternalState) -> dict:
    """Task decomposition: يفكك 'جاهز للتقديم؟' لخطوات محسوسة."""
    print(">>> [RUNNING check_readiness]")

    result = await call_mcp_tool(
        "check_internship_readiness",
        student_id=state["student_id"],
        role_title=state["target_role_title"],
    )
    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", "unknown MCP error")}

    steps = result.get("steps", {})  # {"skills": bool, "cv": bool, "courses": bool, "documents": bool}
    missing_skills = result.get("missing_skills", [])

    if not steps.get("courses", True):
        return {
            "current_state": InternshipState.COURSE_IN_PROGRESS.value,
            "readiness_steps": steps,
            "missing_skills": missing_skills,
        }

    return {
        "current_state": InternshipState.READINESS_CHECKED.value,
        "readiness_steps": steps,
        "missing_skills": missing_skills,
    }


async def node_wait_course_completion(state: GraphInternalState) -> dict:
    """انتظار حقيقي: بيتغير من برة لما الكورس يخلص فعلاً."""
    print(">>> [RUNNING wait_course_completion] -- في انتظار إتمام الكورس")
    signal = get_external_signal(state["thread_id"], "course_completion")
    if signal != "completed":
        return {}  # لسه واقفة هنا
    return {"current_state": InternshipState.SKILL_GAP_ANALYZED.value}  # ارجعي اتشيكي تاني


async def node_hitl_submit_gate(state: GraphInternalState) -> dict:
    """HITL: التقديم الفعلي = أكشن لا رجعة فيه، لازم موافقة قبل الإرسال دايمًا."""
    print(">>> [RUNNING hitl_submit_gate] -- هيتم فتح HITL task")
    return {
        "current_state": InternshipState.AWAITING_HITL_SUBMIT.value,
        "_hitl_request": {
            "reason": "إرسال طلب تدريب فعلي للشركة يحتاج موافقة مستشار/أدمن",
            "details": {
                "student_id": state["student_id"],
                "target_role_title": state["target_role_title"],
                "readiness_steps": state.get("readiness_steps"),
            },
        },
    }


async def node_submit_application(state: GraphInternalState) -> dict:
    """بيتنفذ بس بعد موافقة الأدمن -- إرسال فعلي عبر MCP tool."""
    print(">>> [RUNNING submit_application]")

    result = await call_mcp_tool(
        "submit_internship_application",
        student_id=state["student_id"],
        role_title=state["target_role_title"],
    )
    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", "unknown submit error")}

    application_id = result.get("application_id")
    await call_mcp_tool(
        "update_internship_application_state",
        application_id=application_id,
        new_state=InternshipState.SUBMITTED_AWAITING_COMPANY.value,
    )

    return {
        "current_state": InternshipState.SUBMITTED_AWAITING_COMPANY.value,
        "application_id": application_id,
    }


async def node_await_company_response(state: GraphInternalState) -> dict:
    """انتظار حقيقي: رد الشركة الفعلي (webhook/polling بيحدّث الإشارة دي)."""
    print(">>> [RUNNING await_company_response] -- في انتظار رد الشركة")
    signal = get_external_signal(state["thread_id"], "company_response")
    if signal is None:
        return {}  # لسه واقفة هنا
    if signal == "accepted":
        return {"current_state": InternshipState.COMPANY_ACCEPTED.value}
    return {"current_state": InternshipState.COMPANY_REJECTED.value}


async def node_resolved(state: GraphInternalState) -> dict:
    print(">>> [RUNNING resolved]")
    return {"current_state": InternshipState.RESOLVED.value}


# ---------------------------------------------------------------------------
# 4) التوجيه -- كل دالة بترجع اسم الـ node الجاي، أو None يعني "قف هنا"
# ---------------------------------------------------------------------------

def route_after_skill_gap(state) -> Optional[str]:
    return "check_readiness"

def route_after_readiness(state) -> Optional[str]:
    if state["current_state"] == InternshipState.COURSE_IN_PROGRESS.value:
        return "wait_course_completion"
    return "hitl_submit_gate"

def route_after_wait_course(state) -> Optional[str]:
    if state["current_state"] == InternshipState.COURSE_IN_PROGRESS.value:
        return None  # لسه مستنيين -- قف هنا لحد ما حد ينادي resume تاني
    return "check_readiness"

def route_after_hitl(state) -> Optional[str]:
    # عمليًا الـ runner بيوقف عند hitl_submit_gate بسبب _hitl_request قبل
    # ما يوصل هنا؛ الدالة دي بتتستخدم لما resume بعد قرار الأدمن يكمل يدويًا.
    return "submit_application"

def route_after_submit(state) -> Optional[str]:
    return "await_company_response"

def route_after_await_company(state) -> Optional[str]:
    if state["current_state"] == InternshipState.SUBMITTED_AWAITING_COMPANY.value:
        return None  # لسه مستنيين رد الشركة -- قف هنا
    return "resolved"

ROUTES = {
    "analyze_skill_gap": route_after_skill_gap,
    "check_readiness": route_after_readiness,
    "wait_course_completion": route_after_wait_course,
    "hitl_submit_gate": route_after_hitl,
    "submit_application": route_after_submit,
    "await_company_response": route_after_await_company,
    "resolved": lambda state: None,
}

NODE_FUNCS = {
    "analyze_skill_gap": node_analyze_skill_gap,
    "check_readiness": node_check_readiness,
    "wait_course_completion": node_wait_course_completion,
    "hitl_submit_gate": node_hitl_submit_gate,
    "submit_application": node_submit_application,
    "await_company_response": node_await_company_response,
    "resolved": node_resolved,
}


def _get_ticket_status(ticket_id: int) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM failure_tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row["status"] if row else None


# ---------------------------------------------------------------------------
# 5) الـ Runner -- نفس نمط run_scholarship_graph بالظبط
# ---------------------------------------------------------------------------

async def run_internship_graph(
    thread_id: str,
    start_node: str,
    state: GraphInternalState,
    _crash_after_node: Optional[str] = None,  # للاستخدام في demo فقط
) -> GraphInternalState:
    current_node = start_node

    while current_node is not None:
        node_fn = NODE_FUNCS[current_node]
        update = await node_fn(state)
        state.update(update)
        state["_last_node"] = current_node

        save_checkpoint(thread_id, current_node, dict(state))

        if _crash_after_node == current_node:
            print(">>> [DEMO] محاكاة انهيار العملية الآن (os._exit)")
            os._exit(1)

        if "_hitl_request" in update:
            req = update["_hitl_request"]
            hitl_id = create_hitl_task(thread_id, req["reason"], req.get("details", {}))
            state["pending_hitl_id"] = hitl_id
            save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> توقف عند HITL task #{hitl_id} -- في انتظار قرار الأدمن")
            return state

        if "_ticket_error" in update:
            ticket_id = create_failure_ticket(thread_id, current_node, update["_ticket_error"])
            state["pending_ticket_id"] = ticket_id
            save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> توقف بسبب ticket #{ticket_id} -- في انتظار حل العطل")
            return state

        current_node = ROUTES[current_node](state)

    print(">>> الـ run وصل لنهاية الـ graph أو نقطة انتظار حقيقية.")
    return state


# ---------------------------------------------------------------------------
# 6) نقاط الدخول
# ---------------------------------------------------------------------------

async def start_new_application(
    student_id: int,
    target_role_title: str,
) -> GraphInternalState:
    thread_id = f"internship-{student_id}-{target_role_title}"

    initial_state: GraphInternalState = {
        "application_id": None,
        "student_id": student_id,
        "thread_id": thread_id,
        "target_role_title": target_role_title,
        "missing_skills": None,
        "recommended_courses": None,
        "readiness_steps": None,
        "policy_context": None,
        "current_state": InternshipState.STARTED.value,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }

    save_checkpoint(thread_id, "started", dict(initial_state))
    return await run_or_resume_graph(thread_id)


async def run_or_resume_graph(thread_id: str) -> GraphInternalState:
    """
    نقطة الدخول الموحدة -- نفس نمط graph_2_scholarship.py بالظبط:
    - مفيش checkpoint: خطأ (لازم start_new_application الأول)
    - آخر نقطة كانت HITL pending: بتشيك base مباشرة
    - آخر نقطة كانت ticket مفتوح: بتشيك حالته
    - غير كده: بتكمل من بعد آخر node حسب ROUTES
    """
    from state_graph.base import get_latest_hitl_task

    state = load_latest_checkpoint(thread_id)
    if state is None:
        raise ValueError(f"مفيش checkpoint لـ thread_id={thread_id} -- استخدمي start_new_application الأول.")

    last_node = state.get("_last_node")

    if state.get("pending_hitl_id"):
        task = get_latest_hitl_task(thread_id)
        if task is None or task["status"] == "pending":
            print(">>> لسه في انتظار قرار الأدمن على HITL task.")
            return state

        state["pending_hitl_id"] = None
        if task["status"] == "approved":
            next_node = "submit_application"
        else:
            state["current_state"] = InternshipState.COMPANY_REJECTED.value
            next_node = "resolved"

        return await run_internship_graph(thread_id, start_node=next_node, state=state)

    if state.get("pending_ticket_id"):
        ticket_status = _get_ticket_status(state["pending_ticket_id"])
        if ticket_status != "resolved":
            print(">>> لسه فيه ticket مفتوح، محتاج يتحل الأول.")
            return state

        state["pending_ticket_id"] = None
        return await run_internship_graph(thread_id, start_node=last_node, state=state)

    if last_node is None:
        next_node = "analyze_skill_gap"
    else:
        next_node = ROUTES[last_node](state)

    if next_node is None:
        print(">>> الـ run خلص بالفعل أو لسه واقف عند نقطة انتظار حقيقية.")
        return state

    return await run_internship_graph(thread_id, start_node=next_node, state=state)