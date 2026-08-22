"""
state_graph/graph_2_graduation.py

Graph #2: Graduation Clearance Request

ليه محتاج state graph:
- الطلب بيعدي على 4 فحوصات متتالية (أكاديمي، مالي، مكتبة، مستندات)، وكل
  واحدة ممكن "تفشل" وتحتاج تصحيح من الطالب، وده مش لحظي -- ممكن ياخد أيام
- 4 loops حقيقية: كل فحص فيه مسار "لسه ناقص" بيرجع الطلب لنفس الفحص تاني
  بعد ما الطالب يصلح المشكلة
- القرار النهائي (اعتماد التخرج) قرار لا رجعة فيه -- لازم HITL
- فشل فني حقيقي في أي فحص (مثلاً MCP tool يرجع error) -- ticket، مش قرار

التقنيتان المستخدمتان:
- RAG: node_academic_check بيسحب سياسة متطلبات التخرج الرسمية للقسم.
- Constrained ReAct: كل الفحوصات الأربعة بتستخدم MCP tools محددة سلفًا بس.
"""

from typing import TypedDict, Optional
from enum import Enum

import state_graph.base as base
from state_graph.mcp_client import call_mcp_tool
from state_graph.rag_client import retrieve_scholarship_policy  # نفس الدالة العامة، هنمررلها سؤال مختلف
from state_graph.tickets.dedupe import create_ticket_if_not_open # نفس الدالة العامة، هنمررلها سؤال مختلف

# ---------------------------------------------------------------------------
# 1) الحالات والـ state
# ---------------------------------------------------------------------------

class GraduationState(str, Enum):
    APPLICATION_SUBMITTED = "application_submitted"
    ACADEMIC_CHECK = "academic_check"
    MISSING_COURSE = "missing_course"
    STUDENT_CORRECTION = "student_correction"
    ACADEMIC_OK = "academic_ok"
    FINANCIAL_CHECK = "financial_check"
    FINANCIAL_HOLD = "financial_hold"
    FINANCIAL_CLEAR = "financial_clear"
    LIBRARY_CHECK = "library_check"
    LIBRARY_ISSUE = "library_issue"
    LIBRARY_CLEAR = "library_clear"
    DOCUMENT_CHECK = "document_check"
    MISSING_DOCUMENT = "missing_document"
    STUDENT_UPLOAD = "student_upload"
    DOCUMENT_OK = "document_ok"
    AWAITING_ADMIN_APPROVAL = "awaiting_admin_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class GraphInternalState(TypedDict):
    application_id: int
    student_id: int
    department: str
    thread_id: str

    current_state: str
    total_corrections: int
    max_corrections: int

    policy_context: Optional[str]

    pending_hitl_id: Optional[int]
    pending_ticket_id: Optional[int]
    _last_node: Optional[str]


# ---------------------------------------------------------------------------
# 2) دالة مساعدة عامة لأي فحص (بتقلل تكرار الكود عبر الفحوصات الأربعة)
# ---------------------------------------------------------------------------

async def _run_check(
    state: GraphInternalState,
    tool_name: str,
    ok_state: str,
    problem_state: str,
    extra_kwargs: dict = None,
) -> dict:
    kwargs = {"student_id": state["student_id"], **(extra_kwargs or {})}
    result = await call_mcp_tool(tool_name, **kwargs)

    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", f"{tool_name} فشلت بشكل غير متوقع")}

    if result.get("clear"):
        return {"current_state": ok_state}

    return {"current_state": problem_state}


# ---------------------------------------------------------------------------
# 3) الـ Nodes
# ---------------------------------------------------------------------------

async def node_academic_check(state: GraphInternalState) -> dict:
    """RAG + Constrained ReAct."""
    print(">>> [RUNNING academic_check]")

    print(">>> [RAG] Retrieving graduation policy from shared vector store...")
    policy_text = retrieve_scholarship_policy(
        query=f"graduation requirements for department {state['department']}"
    )
    print(f">>> [RAG] Retrieved text: {policy_text[:150] if policy_text else '(empty -- RAG config needed)'}")

    print(">>> [Constrained ReAct] Calling MCP tool: get_academic_status (only tool allowed here)")
    update = await _run_check(
        state,
        tool_name="get_academic_status",
        ok_state=GraduationState.ACADEMIC_OK.value,
        problem_state=GraduationState.MISSING_COURSE.value,
        extra_kwargs={"department": state["department"]},
    )
    print(f">>> [Constrained ReAct] Tool result: current_state -> {update.get('current_state')}")

    update["policy_context"] = policy_text
    return update


async def node_student_correction(state: GraphInternalState) -> dict:
    """حالة انتظار: الطالب لازم يصلح وضعه الأكاديمي (يسجل مادة ناقصة مثلًا)."""
    print(">>> [RUNNING student_correction] -- waiting for student to fix academic issue")
    return {"total_corrections": state["total_corrections"] + 1}


async def node_financial_check(state: GraphInternalState) -> dict:
    print(">>> [RUNNING financial_check]")
    return await _run_check(
        state, "get_financial_status", GraduationState.FINANCIAL_CLEAR.value, GraduationState.FINANCIAL_HOLD.value
    )


async def node_financial_hold(state: GraphInternalState) -> dict:
    print(">>> [RUNNING financial_hold] -- waiting for outstanding payment")
    return {"total_corrections": state["total_corrections"] + 1}


async def node_library_check(state: GraphInternalState) -> dict:
    print(">>> [RUNNING library_check]")
    return await _run_check(
        state, "get_library_status", GraduationState.LIBRARY_CLEAR.value, GraduationState.LIBRARY_ISSUE.value
    )


async def node_library_issue(state: GraphInternalState) -> dict:
    print(">>> [RUNNING library_issue] -- waiting for book return / fine payment")
    return {"total_corrections": state["total_corrections"] + 1}


async def node_document_check(state: GraphInternalState) -> dict:
    print(">>> [RUNNING document_check]")
    return await _run_check(
        state, "get_required_documents", GraduationState.DOCUMENT_OK.value, GraduationState.MISSING_DOCUMENT.value
    )


async def node_student_upload(state: GraphInternalState) -> dict:
    print(">>> [RUNNING student_upload] -- waiting for document upload")
    return {"total_corrections": state["total_corrections"] + 1}


async def node_admin_approval(state: GraphInternalState) -> dict:
    """HITL node: اعتماد التخرج النهائي قرار لا رجعة فيه."""
    print(">>> [RUNNING admin_approval] -- opening HITL task")
    return {
        "current_state": GraduationState.AWAITING_ADMIN_APPROVAL.value,
        "_hitl_request": {
            "reason": f"اعتماد تخرج الطالب {state['student_id']} -- كل الفحوصات خلصت واستوفت الشروط",
            "details": {
                "graph_type": "graduation",
                "application_id": state["application_id"],
                "department": state["department"],
                "policy_context": state.get("policy_context"),
            },
        },
    }


async def node_approved(state: GraphInternalState) -> dict:
    print(">>> [RUNNING approved]")
    return {"current_state": GraduationState.RESOLVED.value}


async def node_rejected(state: GraphInternalState) -> dict:
    print(">>> [RUNNING rejected]")
    return {"current_state": GraduationState.REJECTED.value}


NODE_FUNCS = {
    "academic_check": node_academic_check,
    "student_correction": node_student_correction,
    "financial_check": node_financial_check,
    "financial_hold": node_financial_hold,
    "library_check": node_library_check,
    "library_issue": node_library_issue,
    "document_check": node_document_check,
    "student_upload": node_student_upload,
    "admin_approval": node_admin_approval,
    "approved": node_approved,
    "rejected": node_rejected,
}


# ---------------------------------------------------------------------------
# 4) دوال التوجيه (routing)
# ---------------------------------------------------------------------------

def _exceeded_corrections(state: GraphInternalState) -> bool:
    return state["total_corrections"] >= state["max_corrections"]


def route_after_academic_check(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == GraduationState.ACADEMIC_OK.value:
        return "financial_check"
    return "student_correction"


def route_after_student_correction(state: GraphInternalState) -> Optional[str]:
    # توقف حقيقي هنا -- الطالب محتاج يسجل مادة ناقصة، ده ممكن ياخد أيام.
    # run_or_resume_graph هو اللي بيقرر يعيد فحص academic_check تاني
    # لما حد ينادي resume، مش الـ loop بيكمل لوحده فورًا.
    return None


def route_after_financial_check(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == GraduationState.FINANCIAL_CLEAR.value:
        return "library_check"
    return "financial_hold"


def route_after_financial_hold(state: GraphInternalState) -> Optional[str]:
    # توقف حقيقي -- في انتظار سداد فعلي من الطالب.
    return None


def route_after_library_check(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == GraduationState.LIBRARY_CLEAR.value:
        return "document_check"
    return "library_issue"


def route_after_library_issue(state: GraphInternalState) -> Optional[str]:
    # توقف حقيقي -- في انتظار إرجاع كتاب/سداد غرامة فعليًا.
    return None


def route_after_document_check(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == GraduationState.DOCUMENT_OK.value:
        return "admin_approval"
    return "student_upload"


def route_after_student_upload(state: GraphInternalState) -> Optional[str]:
    # توقف حقيقي -- في انتظار رفع مستند فعلي من الطالب.
    return None


def route_after_admin_approval(state: GraphInternalState) -> Optional[str]:
    # الـ runner بيوقف عند admin_approval بسبب _hitl_request قبل ما يوصل هنا
    return "approved"


ROUTES = {
    "academic_check": route_after_academic_check,
    "student_correction": route_after_student_correction,
    "financial_check": route_after_financial_check,
    "financial_hold": route_after_financial_hold,
    "library_check": route_after_library_check,
    "library_issue": route_after_library_issue,
    "document_check": route_after_document_check,
    "student_upload": route_after_student_upload,
    "admin_approval": route_after_admin_approval,
    "approved": lambda state: None,
    "rejected": lambda state: None,
}


# ---------------------------------------------------------------------------
# 5) الـ Runner
# ---------------------------------------------------------------------------

async def run_graduation_graph(
    thread_id: str,
    start_node: str = "academic_check",
    state: Optional[GraphInternalState] = None,
    _crash_after_node: Optional[str] = None,
) -> GraphInternalState:
    current_node = start_node

    while current_node is not None:
        node_fn = NODE_FUNCS[current_node]
        update = await node_fn(state)
        state.update(update)
        state["_last_node"] = current_node

        base.save_checkpoint(thread_id, current_node, dict(state))

        if _crash_after_node == current_node:
            print(">>> [DEMO] simulating a process crash now (os._exit)")
            import os
            os._exit(1)

        if "_hitl_request" in update:
            req = update["_hitl_request"]
            hitl_id = base.create_hitl_task(thread_id, req["reason"], req.get("details", {}))
            state["pending_hitl_id"] = hitl_id
            base.save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> Paused at HITL task #{hitl_id}")
            return state

        if "_ticket_error" in update:
            ticket_id = create_ticket_if_not_open(thread_id, current_node, update["_ticket_error"])
            state["pending_ticket_id"] = ticket_id
            base.save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> Paused due to ticket #{ticket_id}")
            return state

        current_node = ROUTES[current_node](state)

    print(">>> Run reached the end of the graph.")
    return state


# ---------------------------------------------------------------------------
# 6) نقاط الدخول
# ---------------------------------------------------------------------------

async def start_new_application(student_id: int, department: str, max_corrections: int = 5) -> GraphInternalState:
    result = await call_mcp_tool("submit_graduation_application", student_id=student_id, department=department)
    if result.get("status") != "success":
        raise RuntimeError(f"فشل تسجيل الطلب: {result.get('message')}")

    application_id = result["application_id"]
    thread_id = f"graduation-{application_id}"

    initial_state: GraphInternalState = {
        "application_id": application_id,
        "student_id": student_id,
        "department": department,
        "thread_id": thread_id,
        "current_state": GraduationState.APPLICATION_SUBMITTED.value,
        "total_corrections": 0,
        "max_corrections": max_corrections,
        "policy_context": None,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }

    base.save_checkpoint(thread_id, "application_submitted", dict(initial_state))
    return await run_or_resume_graph(thread_id)


async def run_or_resume_graph(thread_id: str) -> GraphInternalState:
    """نقطة الدخول الموحدة -- نفس نمط graph_1_study_abroad.py."""
    state = base.load_latest_checkpoint(thread_id)
    if state is None:
        raise ValueError(f"No checkpoint found for thread_id={thread_id} -- call start_new_application first.")

    last_node = state.get("_last_node")

    if state.get("pending_hitl_id"):
        task = base.get_latest_hitl_task(thread_id)
        if task is None or task["status"] == "pending":
            print(">>> Still waiting for admin decision.")
            return state

        state["pending_hitl_id"] = None
        next_node = "approved" if task["status"] == "approved" else "rejected"
        return await run_graduation_graph(thread_id, start_node=next_node, state=state)

    if state.get("pending_ticket_id"):
        ticket_status = _get_ticket_status(state["pending_ticket_id"])
        if ticket_status != "resolved":
            print(">>> Still has an open ticket.")
            return state

        state["pending_ticket_id"] = None
        return await run_graduation_graph(thread_id, start_node=last_node, state=state)

    # نقط الانتظار الحقيقي -- لما حد ينادي resume، لازم نعيد فحص
    # الحالة الأصلية تاني (مش نفترض إن حاجة اتصلحت من غير ما نتأكد)،
    # ونشيك سقف عدد المحاولات هنا بدل ما نلف جوه نفس الاستدعاء المتزامن.
    WAIT_TO_RECHECK = {
        "student_correction": "academic_check",
        "financial_hold": "financial_check",
        "library_issue": "library_check",
        "student_upload": "document_check",
    }

    if last_node in WAIT_TO_RECHECK:
        if _exceeded_corrections(state):
            return await run_graduation_graph(thread_id, start_node="rejected", state=state)
        return await run_graduation_graph(thread_id, start_node=WAIT_TO_RECHECK[last_node], state=state)

    if last_node is None:
        next_node = "academic_check"
    else:
        next_node = ROUTES[last_node](state)

    if next_node is None:
        print(">>> Run already finished.")
        return state

    return await run_graduation_graph(thread_id, start_node=next_node, state=state)


def _get_ticket_status(ticket_id: int) -> Optional[str]:
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM failure_tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row["status"] if row else None