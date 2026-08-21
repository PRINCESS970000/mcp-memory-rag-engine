
 
"""
platform/admin/data_access.py

الطبقة اللي بتقرا/تكتب من الجداول المشتركة (hitl_tasks, failure_tickets)
اللي عاملاها state_graph/base.py، وبتعرف تكمّل أي run بتاع أي graph بعد
ما الأدمن ياخد قرار.

⚠️ اتفاق فريق مطلوب: بما إن hitl_tasks و failure_tickets معندهمش عمود
"graph_type" مباشر، بنعتمد على:
  - HITL: عمود details_json فيه مفتاح "graph_type" (لازم كل graph يحطه)
  - Tickets: بادئة الـ thread_id نفسه (مثال: "scholarship-9999")
لو صاحباتك مش حاطين نفس الاتفاق ده، الجدول ده لازم يتظبط عليهم.
"""

import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# نضيف مسار الريبو الرئيسي عشان نقدر نستورد state_graph كـ package
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ⚠️ مهم: بنضيف فولدر state_graph/ نفسه كمان مباشرة، لأن الملفات جواه
# (زي graph_2_scholarship.py) بتستورد جيرانها بطريقة مسطحة (import base,
# from mcp_client import ...) مش كـ state_graph.base -- ده الاتفاق المتبع
# في كل سكريبتات الفريق (زي demo_crash.py) لما بتتشغل من جوه الفولدر نفسه.
STATE_GRAPH_DIR = str(Path(PROJECT_ROOT) / "state_graph")
if STATE_GRAPH_DIR not in sys.path:
    sys.path.insert(0, STATE_GRAPH_DIR)

import base  # noqa: E402

# سجل الـ graphs -- كل واحد بيسجل نفسه هنا بمفتاح فريد (graph_type)
# ⚠️ لما صاحباتك يخلصوا الـ graphs بتوعهم، لازم يضيفوا سطر هنا برضو
GRAPH_REGISTRY: Dict[str, Any] = {}


def _register_graduation_graph():
    import graph_2_graduation
    GRAPH_REGISTRY["graduation"] = graph_2_graduation.run_or_resume_graph


_register_graduation_graph()


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


def resolve_hitl_and_resume(hitl_id: int, approved: bool) -> Dict[str, Any]:
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

    import asyncio
    run_or_resume_fn = GRAPH_REGISTRY[graph_type]
    result_state = asyncio.run(run_or_resume_fn(task["thread_id"]))

    return {"hitl_id": hitl_id, "graph_type": graph_type, "resulting_state": result_state}


# ---------------------------------------------------------------------------
# Failure tickets
# ---------------------------------------------------------------------------

def list_open_tickets() -> List[Dict[str, Any]]:
    tickets = base.list_open_failure_tickets()
    for t in tickets:
        t["graph_type"] = _infer_graph_type_from_thread_id(t["thread_id"])
    return tickets


def resolve_ticket_and_resume(ticket_id: int) -> Dict[str, Any]:
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

    import asyncio
    run_or_resume_fn = GRAPH_REGISTRY[graph_type]
    result_state = asyncio.run(run_or_resume_fn(ticket["thread_id"]))

    return {"ticket_id": ticket_id, "graph_type": graph_type, "resulting_state": result_state}