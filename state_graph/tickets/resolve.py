"""
state_graph/tickets/resolve.py

دالة موحدة تُستخدم من الأدمن UI: "التذكرة دي اتحلت -- كمّلي الـ thread بتاعها
من checkpoint، مش من الأول". تعمل dispatch لأي graph من التلاتة حسب بادئة
thread_id، عشان تبقى نقطة واحدة يستخدمها platform/user/ بدل ما كل graph
يحتاج شاشة منفصلة.

اتفاق بادئات thread_id بين الفريق (لازم الكل يلتزم بيه):
    scholarship-...   -> graph_2_scholarship
    internship-...    -> graph_3_internship
    (غير كده)         -> graph_1_study_abroad (لسه محتاج بادئة موحدة من
                          الشخص الأول -- دلوقتي بيستخدم أسماء عشوائية زي
                          demo_thread_omar_...، لازم نتفق عليها)
"""

import asyncio
from typing import Any, Dict

from state_graph.base import get_db_connection


def _resolve_failure_ticket_row(ticket_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE failure_tickets SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()


def _get_ticket(ticket_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM failure_tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"مفيش تذكرة برقم {ticket_id}")
    return dict(row)


async def resolve_ticket_and_resume(ticket_id: int) -> Dict[str, Any]:
    """
    1) تعلّم التذكرة resolved.
    2) تعرف الـ thread بتاعها لأي graph.
    3) تنادي run_or_resume_graph بتاعة الـ graph ده -- الاستكمال بيبدأ من
       آخر checkpoint محفوظ، مش من أول الـ graph.
    """
    ticket = _get_ticket(ticket_id)
    thread_id = ticket["thread_id"]

    _resolve_failure_ticket_row(ticket_id)

    if thread_id.startswith("scholarship-"):
        from state_graph.graph_2_scholarship import run_or_resume_graph
        return await run_or_resume_graph(thread_id)

    if thread_id.startswith("internship-"):
        from state_graph.graph_3_internship import run_or_resume_graph
        return await run_or_resume_graph(thread_id)

    # graph_1 لسه sync مش async، والبادئة عندهم مش موحدة -- محتاج يتفق عليها
    from state_graph.graph_1_study_abroad import run_or_resume_graph
    return run_or_resume_graph(thread_id)