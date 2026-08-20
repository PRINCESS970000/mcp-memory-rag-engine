from typing import TypedDict, Optional
from enum import Enum
import os
 
import base
from mcp_client import call_mcp_tool
from rag_client import retrieve_scholarship_policy
 
 
# ---------------------------------------------------------------------------
# 1) تعريف الحالات والـ state
# ---------------------------------------------------------------------------
 
class ScholarshipState(str, Enum):
    APPLICATION_SUBMITTED = "application_submitted"
    AWAITING_SPONSOR_VERIFICATION = "awaiting_sponsor_verification"
    FULL_APPROVAL = "full_approval"
    PARTIAL_APPROVAL = "partial_approval"
    SPONSOR_REJECTED = "sponsor_rejected"
    FUNDING_EXPIRED = "funding_expired"
    STUDENT_APPEAL = "student_appeal"
    AWAITING_ADMIN_APPROVAL = "awaiting_admin_approval"
    DISBURSING = "disbursing"
    ALTERNATIVE_PATH = "alternative_path"
    RESOLVED = "resolved"
 
 
class GraphInternalState(TypedDict):
    """
    الـ state الفعلي اللي base.save_checkpoint بيحفظه (كـ JSON) بعد كل node.
    """
    application_id: int
    student_id: int
    thread_id: str
 
    requested_amount: float
    sponsor_name: Optional[str]
    approved_amount: Optional[float]
 
    current_state: str
 
    appeal_count: int
    max_appeals: int
 
    installments_paid: int
    total_installments: int
 
    policy_context: Optional[str]
 
    pending_hitl_id: Optional[int]
    pending_ticket_id: Optional[int]
 
    _last_node: Optional[str]   # داخلي: آخر node اتنفذ، عشان نعرف نكمل منين
 
 
# ---------------------------------------------------------------------------
# 2) الـ Nodes
#    كل node بيرجع dict فيه إما تحديثات عادية، أو مفتاح خاص:
#      "_hitl_request": {...}   -> الـ runner بينده base.create_hitl_task ويوقف
#      "_ticket_error": "..."   -> الـ runner بينده base.create_failure_ticket ويوقف
# ---------------------------------------------------------------------------
 
async def node_check_eligibility(state: GraphInternalState) -> dict:
    """Constrained ReAct + RAG."""
    print(">>> [RUNNING check_eligibility]")
 
    result = await call_mcp_tool(
        "check_scholarship_eligibility",
        student_id=state["student_id"],
        requested_amount=state["requested_amount"],
    )
 
    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", "unknown MCP error")}
 
    if not result.get("eligible"):
        return {"current_state": ScholarshipState.SPONSOR_REJECTED.value}
 
    policy_text = retrieve_scholarship_policy(
        query=f"شروط أهلية منحة بمبلغ {state['requested_amount']}"
    )
 
    return {
        "current_state": ScholarshipState.AWAITING_SPONSOR_VERIFICATION.value,
        "policy_context": policy_text,
    }
 
 
async def node_await_sponsor(state: GraphInternalState) -> dict:
    """
    حالة انتظار حقيقية. عمدًا مفيش منطق هنا -- current_state بيتغير من برة
    الـ graph (webhook أو استدعاء خارجي بيحدّث الـ checkpoint مباشرة).
    """
    print(">>> [RUNNING await_sponsor] -- في انتظار رد خارجي")
    return {}
 
 
async def node_admin_approval(state: GraphInternalState) -> dict:
    """HITL node: لازم اعتماد أدمن قبل أي صرف فعلي."""
    print(">>> [RUNNING admin_approval] -- هيتم فتح HITL task")
    return {
        "current_state": ScholarshipState.AWAITING_ADMIN_APPROVAL.value,
        "_hitl_request": {
            "reason": f"صرف مبلغ {state['requested_amount']} يحتاج اعتماد أدمن مباشر",
            "details": {
                "application_id": state["application_id"],
                "requested_amount": state["requested_amount"],
                "policy_context": state.get("policy_context"),
            },
        },
    }
 
 
async def node_student_appeal(state: GraphInternalState) -> dict:
    """بيعمل الـ loop: يرجع لـ await_sponsor لحد ما يخلص عدد الاستئنافات."""
    print(">>> [RUNNING student_appeal]")
    new_count = state["appeal_count"] + 1
 
    if new_count >= state["max_appeals"]:
        return {"appeal_count": new_count, "current_state": ScholarshipState.FUNDING_EXPIRED.value}
 
    return {"appeal_count": new_count, "current_state": ScholarshipState.STUDENT_APPEAL.value}
 
 
async def node_disbursement(state: GraphInternalState) -> dict:
    """Constrained ReAct: تنفيذ الصرف الفعلي عبر MCP tool محدد."""
    print(">>> [RUNNING disbursement]")
 
    next_installment_number = state["installments_paid"] + 1
    amount_per_installment = state["requested_amount"] / state["total_installments"]
 
    result = await call_mcp_tool(
        "disburse_installment",
        application_id=state["application_id"],
        installment_number=next_installment_number,
        amount=amount_per_installment,
    )
 
    if result.get("status") != "success":
        return {"_ticket_error": result.get("message", "unknown transfer error")}
 
    new_paid = state["installments_paid"] + 1
    is_done = new_paid >= state["total_installments"]
    new_state = ScholarshipState.RESOLVED.value if is_done else ScholarshipState.AWAITING_SPONSOR_VERIFICATION.value
 
    await call_mcp_tool("update_application_state", application_id=state["application_id"], new_state=new_state)
 
    return {"installments_paid": new_paid, "current_state": new_state}
 
 
async def node_alternative_path(state: GraphInternalState) -> dict:
    print(">>> [RUNNING alternative_path]")
    return {"current_state": ScholarshipState.ALTERNATIVE_PATH.value}
 
 
async def node_resolved(state: GraphInternalState) -> dict:
    print(">>> [RUNNING resolved]")
    return {"current_state": ScholarshipState.RESOLVED.value}
 
 
# ---------------------------------------------------------------------------
# 3) دوال التوجيه (routing) -- بترجع اسم الـ node الجاي، أو None لو النهاية
# ---------------------------------------------------------------------------
 
def route_after_check_eligibility(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == ScholarshipState.SPONSOR_REJECTED.value:
        return "student_appeal"
    return "await_sponsor"
 
 
def route_after_sponsor(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] in (ScholarshipState.FULL_APPROVAL.value, ScholarshipState.PARTIAL_APPROVAL.value):
        return "admin_approval"
    return "student_appeal"
 
 
def route_after_appeal(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == ScholarshipState.FUNDING_EXPIRED.value:
        return "alternative_path"
    return "await_sponsor"   # <-- الـ loop
 
 
def route_after_admin_approval(state: GraphInternalState) -> Optional[str]:
    # عمليًا الـ runner بيوقف عند admin_approval بسبب _hitl_request قبل ما
    # يوصل هنا؛ الدالة دي بتتستخدم بس لما resume_after_admin_decision يكمل يدويًا.
    return "disbursement"
 
 
def route_after_disbursement(state: GraphInternalState) -> Optional[str]:
    if state["current_state"] == ScholarshipState.RESOLVED.value:
        return "resolved"
    return "await_sponsor"   # <-- loop الأقساط
 
 
ROUTES = {
    "check_eligibility": route_after_check_eligibility,
    "await_sponsor": route_after_sponsor,
    "student_appeal": route_after_appeal,
    "admin_approval": route_after_admin_approval,
    "disbursement": route_after_disbursement,
    "alternative_path": lambda state: None,
    "resolved": lambda state: None,
}
 
NODE_FUNCS = {
    "check_eligibility": node_check_eligibility,
    "await_sponsor": node_await_sponsor,
    "admin_approval": node_admin_approval,
    "student_appeal": node_student_appeal,
    "disbursement": node_disbursement,
    "alternative_path": node_alternative_path,
    "resolved": node_resolved,
}
 
 
def _get_ticket_status(ticket_id: int) -> Optional[str]:
    """base.py معندهاش دالة get لتذكرة واحدة بالـ id، فبنستخدم نفس اتصالها مباشرة."""
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM failure_tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row["status"] if row else None
 
 
def _resolve_failure_ticket(ticket_id: int) -> None:
    """بتتنادى من شاشة الأدمن لما يتأكد إن العطل اتصلح يدويًا."""
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE failure_tickets SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()
 
 
# ---------------------------------------------------------------------------
# 4) الـ Runner -- بيمشي على الـ nodes ويحفظ checkpoint بعد كل واحدة
# ---------------------------------------------------------------------------
 
async def run_scholarship_graph(
    thread_id: str,
    start_node: str = "check_eligibility",
    state: Optional[GraphInternalState] = None,
    _crash_after_node: Optional[str] = None,   # للاستخدام في demo_crash_resume.py بس
) -> GraphInternalState:
    """
    بتنفذ الـ graph node by node، وبتحفظ checkpoint (عن طريق base.save_checkpoint)
    بعد كل node، وبتوقف فورًا لو الـ node طلب HITL أو فتح ticket.
    """
    current_node = start_node
 
    while current_node is not None:
        node_fn = NODE_FUNCS[current_node]
        update = await node_fn(state)
        state.update(update)
        state["_last_node"] = current_node
 
        # الحفظ بيحصل هنا -- بعد كل node على طول، مش بس في الآخر
        base.save_checkpoint(thread_id, current_node, dict(state))
 
        if _crash_after_node == current_node:
            print(">>> [DEMO] محاكاة انهيار العملية الآن (os._exit)")
            import sys
            os._exit(1)
 
        if "_hitl_request" in update:
            req = update["_hitl_request"]
            hitl_id = base.create_hitl_task(thread_id, req["reason"], req.get("details", {}))
            state["pending_hitl_id"] = hitl_id
            base.save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> توقف عند HITL task #{hitl_id} -- في انتظار قرار الأدمن")
            return state
 
        if "_ticket_error" in update:
            ticket_id = base.create_failure_ticket(thread_id, current_node, update["_ticket_error"])
            state["pending_ticket_id"] = ticket_id
            base.save_checkpoint(thread_id, current_node, dict(state))
            print(f">>> توقف بسبب ticket #{ticket_id} -- في انتظار حل العطل")
            return state
 
        current_node = ROUTES[current_node](state)
 
    print(">>> الـ run وصل لنهاية الـ graph.")
    return state
 
 
# ---------------------------------------------------------------------------
# 5) نقاط الدخول: بدء طلب جديد، والاستئناف بعد HITL أو بعد حل ticket
# ---------------------------------------------------------------------------
 
async def start_new_application(
    student_id: int,
    requested_amount: float,
    sponsor_name: Optional[str] = None,
    total_installments: int = 3,
    max_appeals: int = 2,
) -> GraphInternalState:
    """
    بتنادى مرة واحدة بس عشان تسجل الطلب في الداتابيز وتحدد الـ thread_id.
    بعد كده كل تشغيل/استكمال بيتم عن طريق run_or_resume_graph فقط.
    """
    result = await call_mcp_tool(
        "submit_scholarship_application",
        student_id=student_id,
        requested_amount=requested_amount,
        sponsor_name=sponsor_name,
    )
    if result.get("status") != "success":
        raise RuntimeError(f"فشل تسجيل الطلب: {result.get('message')}")
 
    application_id = result["application_id"]
    thread_id = f"scholarship-{application_id}"
 
    initial_state: GraphInternalState = {
        "application_id": application_id,
        "student_id": student_id,
        "thread_id": thread_id,
        "requested_amount": requested_amount,
        "sponsor_name": sponsor_name,
        "approved_amount": None,
        "current_state": ScholarshipState.APPLICATION_SUBMITTED.value,
        "appeal_count": 0,
        "max_appeals": max_appeals,
        "installments_paid": 0,
        "total_installments": total_installments,
        "policy_context": None,
        "pending_hitl_id": None,
        "pending_ticket_id": None,
        "_last_node": None,
    }
 
    # أول checkpoint، عشان run_or_resume_graph يلاقي حاجة يبدأ منها
    base.save_checkpoint(thread_id, "application_submitted", dict(initial_state))
 
    return await run_or_resume_graph(thread_id)
 
 
async def run_or_resume_graph(thread_id: str) -> GraphInternalState:
    """
    نقطة الدخول الموحدة للـ graph -- نفس النمط المتبع في graph_1_study_abroad.py.
    بتشتغل بنفس الطريقة سواء أول مرة أو عشان تكمل run متوقف:
    - لو مفيش checkpoint خالص: بترفض (لازم يتنادى start_new_application الأول)
    - لو آخر node كانت متوقفة عند HITL: بتشيك حالة الـ task في base.py،
      لو لسه pending بترجع نفس الـ state من غير ما تتحرك خطوة.
    - لو آخر node كانت متوقفة عند ticket: بتشيك حالته بنفس المنطق.
    - غير كده: بتكمل من الـ node اللي بعد آخر واحدة اتنفذت، حسب ROUTES.
    """
    state = base.load_latest_checkpoint(thread_id)
    if state is None:
        raise ValueError(
            f"مفيش checkpoint لـ thread_id={thread_id} -- استخدمي start_new_application الأول."
        )
 
    last_node = state.get("_last_node")
 
    if state.get("pending_hitl_id"):
        task = base.get_latest_hitl_task(thread_id)
        if task is None or task["status"] == "pending":
            print(">>> لسه في انتظار قرار الأدمن على HITL task.")
            return state
 
        state["pending_hitl_id"] = None
        if task["status"] == "approved":
            next_node = "disbursement"
        else:
            state["current_state"] = ScholarshipState.ALTERNATIVE_PATH.value
            next_node = "alternative_path"
 
        return await run_scholarship_graph(thread_id, start_node=next_node, state=state)
 
    if state.get("pending_ticket_id"):
        ticket_status = _get_ticket_status(state["pending_ticket_id"])
        if ticket_status != "resolved":
            print(">>> لسه فيه ticket مفتوح، محتاج يتحل الأول.")
            return state
 
        state["pending_ticket_id"] = None
        # الاستكمال بعد حل ticket بيعيد تنفيذ نفس الـ node اللي فشلت
        return await run_scholarship_graph(thread_id, start_node=last_node, state=state)
 
  
    if last_node is None:
        next_node = "check_eligibility"
    else:
        next_node = ROUTES[last_node](state)
 
    if next_node is None:
        print(">>> الـ run خلص بالفعل.")
        return state
 
    return await run_scholarship_graph(thread_id, start_node=next_node, state=state)