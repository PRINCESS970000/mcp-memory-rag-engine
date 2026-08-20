"""
state_graph/checkpointing/base.py

الطبقة المشتركة (Shared Infrastructure) اللي بتستخدمها كل الـ State Graphs التلاتة.
لازم كل graph يستورد من هنا مباشرة، ومفيش أي graph يعمل نسخة تانية من الجداول
دي أو يفتح قاعدة بيانات مختلفة.

الجداول:
1. checkpoints       -> حفظ آخر state لكل (thread_id, node_name) لإثبات crash-and-resume
2. hitl_tasks         -> مهام تنتظر موافقة/رفض بشري (Admin) قبل ما الـ graph يكمل
3. failure_tickets    -> تذاكر بتوثق أي فشل غير متوقع (تفشل أداة MCP / validation)
"""

import json
import sqlite3
import os
from typing import Any, Dict, List, Optional

# مسار واحد موحّد لكل الـ graphs الثلاثة - محدش يغيّره في نسخته
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "db", "brightpeak.db")
DB_PATH = os.path.abspath(DB_PATH)


def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_checkpointing_tables() -> None:
    """إنشاء الجداول المشتركة لو مش موجودة. Idempotent - ممكن تتنادى أي وقت."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # ملاحظة مهمة: استخدمنا "id" كـ AUTOINCREMENT عشان نحصل على ترتيب حقيقي
    # لآخر checkpoint. الاعتماد على updated_at لوحده كان بيفشل لأن SQLite
    # بيسجّل CURRENT_TIMESTAMP بدقة الثانية فقط، وكل الـ nodes في نفس الـ run
    # غالبًا بتتنفذ في نفس الثانية، فبيرجع صف عشوائي بدل آخر node حقيقي.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            node_name TEXT NOT NULL,
            state_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (thread_id, node_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hitl_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            required_role TEXT DEFAULT 'ADMIN',
            details_json TEXT,
            status TEXT DEFAULT 'pending', -- 'pending' | 'approved' | 'rejected'
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failure_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            node_name TEXT NOT NULL,
            error_message TEXT NOT NULL,
            status TEXT DEFAULT 'open', -- 'open' | 'investigating' | 'resolved'
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)

    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Checkpointing
# ------------------------------------------------------------------

def save_checkpoint(thread_id: str, node_name: str, state: Dict[str, Any]) -> None:
    """حفظ الحالة فورًا بعد كل node - ده اللي بيسمح بالـ crash-and-resume."""
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO checkpoints (thread_id, node_name, state_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (thread_id, node_name, json.dumps(state, ensure_ascii=False)))
    conn.commit()
    conn.close()


def load_latest_checkpoint(thread_id: str) -> Optional[Dict[str, Any]]:
    """استرجاع آخر state محفوظ لـ thread_id معيّن، أو None لو graph جديد."""
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT state_json FROM checkpoints
        WHERE thread_id = ?
        ORDER BY id DESC LIMIT 1
    """, (thread_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["state_json"])
    return None


# ------------------------------------------------------------------
# HITL (Human-in-the-loop)
# ------------------------------------------------------------------

def create_hitl_task(thread_id: str, reason: str, details: Dict[str, Any],
                      required_role: str = "ADMIN") -> int:
    """إنشاء مهمة تدخل بشري. الـ graph بيوقف هنا لحد ما حد يرد على المهمة."""
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hitl_tasks (thread_id, reason, required_role, details_json)
        VALUES (?, ?, ?, ?)
    """, (thread_id, reason, required_role, json.dumps(details, ensure_ascii=False)))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def get_latest_hitl_task(thread_id: str) -> Optional[Dict[str, Any]]:
    """آخر مهمة HITL لـ thread_id معيّن - ده اللي الـ graph بيفحصه عند الاستئناف."""
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM hitl_tasks
        WHERE thread_id = ?
        ORDER BY id DESC LIMIT 1
    """, (thread_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def resolve_hitl_task(task_id: int, status: str) -> None:
    """يستخدمها الأدمن (أو سكريبت المحاكاة) لتحديث حالة المهمة إلى approved/rejected."""
    if status not in ("approved", "rejected"):
        raise ValueError("status must be 'approved' or 'rejected'")
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE hitl_tasks
        SET status = ?, resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, task_id))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Failure tickets
# ------------------------------------------------------------------

def create_failure_ticket(thread_id: str, node_name: str, error_msg: str) -> int:
    """تذكرة توثّق فشل حقيقي (مش HITL) - مثلاً فشل استدعاء أداة MCP."""
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO failure_tickets (thread_id, node_name, error_message)
        VALUES (?, ?, ?)
    """, (thread_id, node_name, error_msg))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id


def list_open_failure_tickets() -> List[Dict[str, Any]]:
    init_checkpointing_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM failure_tickets WHERE status = 'open'")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows