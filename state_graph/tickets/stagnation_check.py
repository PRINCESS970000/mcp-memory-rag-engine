"""
state_graph/tickets/stagnation_check.py

فحص دوري حقيقي لاكتشاف الركود (stagnation): thread واقف في حالة "بينتظر رد
خارجي" لفترة أطول من المعقول، من غير ما حد يتدخل يدويًا.

يُفترض تشغيل هذا السكريبت بشكل متكرر (cron / scheduled task) -- مثلاً كل
5 دقايق -- مش استدعاء يدوي وقت الحاجة. هذا هو الفرق الجوهري بينه وبين
_ticket_error العادي اللي بيتفعّل فورًا جوه الـ node نفسه.

مبدأ العمل:
1) يجيب آخر checkpoint لكل thread_id مختلف.
2) لو current_state/status بتاعه من ضمن "حالات الانتظار الخارجي" المعروفة
   لهذا الـ graph، ولو الوقت اللي فات من آخر تحديث أكبر من STAGNATION_THRESHOLDS
   الخاصة بالحالة دي -> يفتح ticket، لكن **مرة واحدة بس** لكل (thread, node)
   -- بيتفادى فتح تذاكر مكررة لنفس الركود في كل تشغيلة.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional

from state_graph.base import get_db_connection, create_failure_ticket

# الحالات اللي معناها "بننتظر رد خارجي حقيقي" لكل graph، وبعد قد إيه
# نعتبرها ركود. الوقت هنا بالدقايق -- في الديمو نخليها صغيرة، وفي
# الإنتاج الحقيقي المفروض تتغير لساعات/أيام حسب طبيعة كل انتظار.
STAGNATION_RULES: Dict[str, timedelta] = {
    "pending_external": timedelta(minutes=30),          # graph_1 (study abroad)
    "awaiting_sponsor_verification": timedelta(minutes=30),  # graph_2 (scholarship)
    "course_in_progress": timedelta(hours=2),             # graph_3 (internship: كورس)
    "submitted_awaiting_company": timedelta(minutes=30),   # graph_3 (internship: رد شركة)
}

# اسم الحقل اللي بيحمل الحالة يختلف بين graph_1 (status) والباقي (current_state)
STATE_FIELD_CANDIDATES = ["current_state", "status"]


def _get_all_latest_checkpoints() -> list:
    """آخر checkpoint فعلي لكل thread_id مختلف، مع وقت آخر تحديث."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c1.thread_id, c1.node_name, c1.state_json, c1.updated_at
        FROM checkpoints c1
        INNER JOIN (
            SELECT thread_id, MAX(id) as max_id
            FROM checkpoints
            GROUP BY thread_id
        ) c2 ON c1.thread_id = c2.thread_id AND c1.id = c2.max_id
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _extract_state_value(state_json: str) -> Optional[str]:
    import json
    state = json.loads(state_json)
    for field in STATE_FIELD_CANDIDATES:
        if field in state:
            return state[field]
    return None


def _already_has_open_stagnation_ticket(thread_id: str, node_name: str) -> bool:
    """بيمنع تكرار فتح تذاكر لنفس الركود في كل تشغيلة للفحص."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM failure_tickets
        WHERE thread_id = ? AND node_name = ?
          AND status IN ('open', 'investigating')
          AND error_message LIKE '[STAGNATION]%'
    """, (thread_id, node_name))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def run_stagnation_check() -> list:
    """
    الدالة اللي المفروض تتشغل دوريًا (cron/scheduled task). بترجع list
    بالـ ticket_ids الجديدة اللي اتفتحت في التشغيلة دي (فاضية لو مفيش ركود).
    """
    opened_tickets = []
    now = datetime.utcnow()

    for row in _get_all_latest_checkpoints():
        state_value = _extract_state_value(row["state_json"])
        if state_value not in STAGNATION_RULES:
            continue  # مش حالة انتظار خارجي معروفة -- تجاهل

        updated_at = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S")
        threshold = STAGNATION_RULES[state_value]

        if now - updated_at < threshold:
            continue  # لسه في الوقت المعقول -- مفيش ركود حقيقي بعد

        if _already_has_open_stagnation_ticket(row["thread_id"], row["node_name"]):
            continue  # فيه تذكرة مفتوحة بالفعل لنفس الحالة -- ماتفتحيش تانية

        ticket_id = create_failure_ticket(
            thread_id=row["thread_id"],
            node_name=row["node_name"],
            error_message=(
                f"[STAGNATION] لا رد خارجي منذ {now - updated_at} "
                f"(الحالة: {state_value}, الحد المسموح: {threshold})"
            ),
        )
        opened_tickets.append(ticket_id)
        print(f">>> [Stagnation Check] فُتحت تذكرة #{ticket_id} لـ thread={row['thread_id']}")

    return opened_tickets


if __name__ == "__main__":
    run_stagnation_check()