import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
 
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
 
STATE_GRAPH_DIR = str(Path(PROJECT_ROOT) / "state_graph")
if STATE_GRAPH_DIR not in sys.path:
    sys.path.insert(0, STATE_GRAPH_DIR)
 
import base  # noqa: E402

GRAPH_REGISTRY: Dict[str, Any] = {}
 
 
def _register_graduation_graph():
    import graph_2_graduation
    GRAPH_REGISTRY["graduation"] = graph_2_graduation.run_or_resume_graph
 
 
def _register_internship_graph():
    import graph_3_internship
    GRAPH_REGISTRY["internship"] = graph_3_internship.run_or_resume_graph
 
 
def _register_study_abroad_graph():
    # graph_1_study_abroad.run_or_resume_graph is defined as a plain
    # "def" (sync), while graduation/internship are "async def". Every
    # caller in this file does `await run_or_resume_fn(...)`, so
    # registering the sync function directly would raise
    # "object dict can't be used in 'await' expression" the first time
    # an admin resolves a study_abroad HITL task/ticket. Wrapped here
    # instead of editing graph_1 itself, to keep this a one-file fix.
    import graph_1_study_abroad

    async def _resume(thread_id):
        return graph_1_study_abroad.run_or_resume_graph(thread_id)

    GRAPH_REGISTRY["study_abroad"] = _resume
 
 
_register_graduation_graph()
_register_internship_graph()
_register_study_abroad_graph()
 
 
def _infer_graph_type_from_thread_id(thread_id: str) -> Optional[str]:
    """بديل احتياطي لو مفيش graph_type محفوظ صراحة -- بيدور على أقرب مفتاح مطابق."""
    for key in GRAPH_REGISTRY:
        if thread_id.startswith(key):
            return key
    return None
 
 
# ---------------------------------------------------------------------------
# HITL tasks
# ---------------------------------------------------------------------------
 
def list_pending_hitl_tasks() -> List[Dict[str, Any]]:
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hitl_tasks WHERE status = 'pending' ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
 
    for row in rows:
        details = json.loads(row["details_json"]) if row.get("details_json") else {}
        row["details"] = details
        row["graph_type"] = details.get("graph_type") or _infer_graph_type_from_thread_id(row["thread_id"])
 
    return rows
 
 
async def resolve_hitl_and_resume(hitl_id: int, approved: bool) -> Dict[str, Any]:
    """
    بتنادى من شاشة الأدمن. بتحدّث حالة الـ task، وبعدين بتنادي run_or_resume_graph
    بتاع الـ graph الصح تلقائيًا (حسب graph_type المسجل وقت فتح الـ task).
    """
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hitl_tasks WHERE id = ?", (hitl_id,))
    row = cursor.fetchone()
    conn.close()
 
    if row is None:
        raise ValueError(f"مفيش HITL task برقم {hitl_id}")
 
    task = dict(row)
    details = json.loads(task["details_json"]) if task.get("details_json") else {}
    graph_type = details.get("graph_type") or _infer_graph_type_from_thread_id(task["thread_id"])
 
    if graph_type not in GRAPH_REGISTRY:
        raise ValueError(
            f"graph_type='{graph_type}' مش مسجل في GRAPH_REGISTRY -- "
            f"لازم يتضاف هنا الأول من data_access.py"
        )
 
    base.resolve_hitl_task(hitl_id, "approved" if approved else "rejected")
 
    run_or_resume_fn = GRAPH_REGISTRY[graph_type]
    result_state = await run_or_resume_fn(task["thread_id"])
 
    return {"hitl_id": hitl_id, "graph_type": graph_type, "resulting_state": result_state}
 
 
# ---------------------------------------------------------------------------
# Failure tickets
# ---------------------------------------------------------------------------
 
def list_open_tickets() -> List[Dict[str, Any]]:
    tickets = base.list_open_failure_tickets()
    for t in tickets:
        t["graph_type"] = _infer_graph_type_from_thread_id(t["thread_id"])
    return tickets
 
 
async def resolve_ticket_and_resume(ticket_id: int) -> Dict[str, Any]:
    """بتنادى بعد ما الأدمن يتأكد إن العطل اتصلح يدويًا -- بتعيد محاولة نفس الـ node."""
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM failure_tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
 
    if row is None:
        conn.close()
        raise ValueError(f"مفيش ticket برقم {ticket_id}")
 
    ticket = dict(row)
    graph_type = _infer_graph_type_from_thread_id(ticket["thread_id"])
 
    cursor.execute(
        "UPDATE failure_tickets SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()
 
    if graph_type not in GRAPH_REGISTRY:
        raise ValueError(f"graph_type='{graph_type}' مش مسجل في GRAPH_REGISTRY")
 
    run_or_resume_fn = GRAPH_REGISTRY[graph_type]
    result_state = await run_or_resume_fn(ticket["thread_id"])
 
    return {"ticket_id": ticket_id, "graph_type": graph_type, "resulting_state": result_state}
 
 
# ---------------------------------------------------------------------------
# MCP Tools management (runtime enable/disable)
# ---------------------------------------------------------------------------
 
def list_mcp_tools() -> list:
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tool_name, enabled FROM mcp_tool_status ORDER BY tool_name")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
 
 
def toggle_mcp_tool(tool_name: str) -> dict:
    conn = base.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT enabled FROM mcp_tool_status WHERE tool_name = ?", (tool_name,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Unknown tool: {tool_name}")
 
    new_value = 0 if row["enabled"] else 1
    cursor.execute("UPDATE mcp_tool_status SET enabled = ? WHERE tool_name = ?", (new_value, tool_name))
    conn.commit()
    conn.close()
    return {"tool_name": tool_name, "enabled": bool(new_value)}