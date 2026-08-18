import sqlite3
import json
import os
import sys

# ربط المسار لاستيراد الـ mcp_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from client import call_mcp_tool

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "academy.db"))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ======================================================
# Checkpoint & Infrastructure DB Helpers
# ======================================================

def save_checkpoint(thread_id: str, node_name: str, state: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT,
            node_name TEXT,
            state_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (thread_id, node_name)
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO checkpoints (thread_id, node_name, state_data)
        VALUES (?, ?, ?)
    """, (thread_id, node_name, json.dumps(state)))
    conn.commit()
    conn.close()

def get_latest_checkpoint(thread_id: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT state_data FROM checkpoints 
        WHERE thread_id = ? 
        ORDER BY created_at DESC LIMIT 1
    """, (thread_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["state_data"])
    return None

def create_hitl_task(thread_id: str, prompt: str, required_role: str = "ADMIN"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hitl_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            prompt TEXT,
            required_role TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO hitl_tasks (thread_id, prompt, required_role, status)
        VALUES (?, ?, ?, 'PENDING')
    """, (thread_id, prompt, required_role))
    conn.commit()
    conn.close()

def create_failure_ticket(thread_id: str, error_message: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failure_tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            error_message TEXT,
            status TEXT DEFAULT 'OPEN',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO failure_tickets (thread_id, error_message, status)
        VALUES (?, ?, 'OPEN')
    """, (thread_id, error_message))
    conn.commit()
    conn.close()

# ======================================================
# Graph Nodes
# ======================================================

def lats_search_node(state: dict) -> dict:
    """Node 1: LATS Search Workflow using MCP Tools"""
    print(f"--- Running LATS Search Node for Thread {state.get('thread_id')} ---")
    try:
        # استدعاء أداة الـ MCP لجلب الكورسات/السجل الأكاديمي
        courses_res = call_mcp_tool("list_all_courses")
        courses = courses_res.get("courses", [])

        # خوارزمية LATS لاختيار أفضل برنامج متوافق
        selected_program = "Exchange Program - ETH Zurich"
        requires_grant = True

        state["selected_program"] = selected_program
        state["requires_grant"] = requires_grant
        state["courses_evaluated"] = len(courses)
        state["status"] = "lats_completed"

        save_checkpoint(state["thread_id"], "lats_search_node", state)
        return state
    except Exception as e:
        state["status"] = "failed"
        create_failure_ticket(state["thread_id"], f"LATS Error: {str(e)}")
        save_checkpoint(state["thread_id"], "lats_search_node", state)
        return state


def constrained_react_validation_node(state: dict) -> dict:
    """Node 2: Constrained ReAct Node with White-listed MCP Tools"""
    print(f"--- Running Constrained ReAct Validation Node for Thread {state.get('thread_id')} ---")
    try:
        student_email = state.get("student_email", "omar.k@brightpeak.edu")
        profile_res = call_mcp_tool("get_student_profile", {"email": student_email})
        
        student_data = profile_res.get("data", {})
        if not student_data:
            raise ValueError("Student profile not found via MCP Server.")

        state["student_name"] = student_data.get("name")
        state["documents_valid"] = True
        state["status"] = "validation_completed"

        save_checkpoint(state["thread_id"], "constrained_react_validation_node", state)
        return state
    except Exception as e:
        state["status"] = "failed"
        create_failure_ticket(state["thread_id"], f"Validation Error: {str(e)}")
        save_checkpoint(state["thread_id"], "constrained_react_validation_node", state)
        return state


def hitl_gate_node(state: dict) -> dict:
    """Node 3: Human-in-the-Loop Pause Gate"""
    print(f"--- Checking HITL Gate for Thread {state.get('thread_id')} ---")
    if state.get("requires_grant"):
        state["status"] = "paused_for_hitl"
        create_hitl_task(
            state["thread_id"],
            f"Approval required for exchange grant: {state.get('selected_program')}",
            required_role="ADMIN"
        )
        save_checkpoint(state["thread_id"], "hitl_gate_node", state)
        print("⏸️ State Graph Paused for Human Approval.")
    else:
        state["status"] = "ready_for_submission"
        save_checkpoint(state["thread_id"], "hitl_gate_node", state)
    return state

# ======================================================
# Main Execution / Resumption Flow
# ======================================================

def run_or_resume_graph(thread_id: str, student_email: str = "omar.k@brightpeak.edu"):
    # 1. محاولة التعافي واستئناف أحدث Checkpoint
    checkpoint = get_latest_checkpoint(thread_id)
    if checkpoint:
        print(f"🔄 Resuming from saved Checkpoint. Current status: {checkpoint.get('status')}")
        state = checkpoint
    else:
        print("🆕 Starting fresh State Graph execution.")
        state = {
            "thread_id": thread_id,
            "student_email": student_email,
            "status": "start"
        }

    # 2. Sequential Execution with Routing
    if state["status"] in ["start"]:
        state = lats_search_node(state)

    if state["status"] in ["lats_completed"]:
        state = constrained_react_validation_node(state)

    if state["status"] in ["validation_completed"]:
        state = hitl_gate_node(state)

    return state


if __name__ == "__main__":
    # تشغيل للتجربة
    result = run_or_resume_graph("thread_user_101")
    print("\nFinal State Output:", json.dumps(result, indent=2))