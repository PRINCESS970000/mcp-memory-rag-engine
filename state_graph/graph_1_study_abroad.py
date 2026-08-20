"""
state_graph/graph_1_study_abroad/graph.py

Graph #3: Study Abroad & Internship Placement Coordination Graph

Why a State Graph?
- Long-running continuity: submission -> waiting for the host university /
  company response -> travel/internship paperwork -> final signature.
- External branch: the placement outcome depends on a response from an
  external party (company or university) and interview scheduling.
- Failure mode: an external rejection or an application deadline timeout
  must redirect the student to a second-choice preference without losing
  any of the already-completed application data.

Techniques used inside the nodes:
- LATS (Language Agent Tree Search)  -> lats_search_node
- Constrained ReAct                  -> constrained_react_validation_node

HITL: final signature on the nomination letter and/or financial grant
approval always requires direct Admin sign-off -> hitl_gate_node
"""

import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Shared infrastructure layer - no local re-implementation of checkpoint
# logic lives in this file.
from state_graph.base import (
    get_db_connection,
    save_checkpoint,
    load_latest_checkpoint,
    create_hitl_task,
    get_latest_hitl_task,
    create_failure_ticket,
)

try:
    from client import call_mcp_tool
except ImportError:
    # Simple standalone fallback for running/testing this graph in isolation
    # when the repo's real client/ module isn't available in this environment.
    def call_mcp_tool(tool_name: str, args: dict = None):
        print(f"[MCP STUB] calling {tool_name} with {args}")
        if tool_name == "list_all_courses":
            return {"courses": ["CS101", "MATH201", "ECON301"]}
        if tool_name == "get_student_profile":
            return {"data": {"name": "Omar Khaled", "gpa": 3.6}}
        if tool_name == "submit_application":
            return {"submitted": True, "application_id": "APP-0001"}
        return {}


MAX_PREFERENCE_ATTEMPTS = 3  # safety guard against an infinite loop if every option gets rejected


# ======================================================
# Domain-specific helpers (belong to this graph only, not shared infra)
# ======================================================

def init_domain_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_abroad_external_signals (
            thread_id TEXT,
            preference_index INTEGER,
            signal TEXT, -- 'approved' | 'rejected' | 'timeout' | NULL (no response yet)
            PRIMARY KEY (thread_id, preference_index)
        )
    """)
    conn.commit()
    conn.close()


def set_external_signal(thread_id: str, preference_index: int, signal: str):
    """Used by a simulation script / the host organization to record a real-world response."""
    init_domain_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO study_abroad_external_signals (thread_id, preference_index, signal)
        VALUES (?, ?, ?)
    """, (thread_id, preference_index, signal))
    conn.commit()
    conn.close()


def get_external_signal(thread_id: str, preference_index: int):
    init_domain_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT signal FROM study_abroad_external_signals
        WHERE thread_id = ? AND preference_index = ?
    """, (thread_id, preference_index))
    row = cursor.fetchone()
    conn.close()
    return row["signal"] if row else None


# ======================================================
# Graph Nodes
# ======================================================

def lats_search_node(state: dict) -> dict:
    """Node: LATS - search/ranking across the best available opportunities
    based on the student's requirements, academic record, and finances."""
    tid = state["thread_id"]
    print(f"--- [LATS] Search Node | thread={tid} pref_idx={state.get('preference_index', 0)} ---")
    try:
        courses_res = call_mcp_tool("list_all_courses")
        courses = courses_res.get("courses", [])

        # Fixed candidate list for this demo (a real Tree Search would score
        # and rank these) - built only once per thread.
        if "program_choices" not in state:
            state["program_choices"] = [
                {"name": "Exchange Program - ETH Zurich", "requires_grant": True},
                {"name": "Internship - Siemens Munich", "requires_grant": True},
                {"name": "Exchange Program - NUS Singapore", "requires_grant": False},
            ]

        idx = state.get("preference_index", 0)
        if idx >= len(state["program_choices"]):
            state["status"] = "no_more_options"
            state["failure_reason"] = "All available options were rejected or timed out"
            save_checkpoint(tid, "lats_search_node", state)
            return state

        chosen = state["program_choices"][idx]
        state["selected_program"] = chosen["name"]
        state["requires_grant"] = chosen["requires_grant"]
        state["courses_evaluated"] = len(courses)
        state["status"] = "lats_completed"

        save_checkpoint(tid, "lats_search_node", state)
        return state
    except Exception as e:
        state["status"] = "failed"
        create_failure_ticket(tid, "lats_search_node", f"LATS Error: {str(e)}")
        save_checkpoint(tid, "lats_search_node", state)
        return state


def constrained_react_validation_node(state: dict) -> dict:
    """Node: Constrained ReAct - verify required documents and call only
    whitelisted MCP tools."""
    tid = state["thread_id"]
    print(f"--- [Constrained ReAct] Validation Node | thread={tid} ---")
    try:
        # If the profile was already validated before (e.g. after a
        # redirect), there's no need to call the MCP tool again.
        if not state.get("student_name"):
            profile_res = call_mcp_tool("get_student_profile", {"email": state.get("student_email")})
            student_data = profile_res.get("data", {})
            if not student_data:
                raise ValueError("Student profile not found via MCP Server.")
            state["student_name"] = student_data.get("name")

        state["documents_valid"] = True
        state["status"] = "validation_completed"
        save_checkpoint(tid, "constrained_react_validation_node", state)
        return state
    except Exception as e:
        state["status"] = "failed"
        create_failure_ticket(tid, "constrained_react_validation_node", f"Validation Error: {str(e)}")
        save_checkpoint(tid, "constrained_react_validation_node", state)
        return state


def submit_application_node(state: dict) -> dict:
    """Node: submit the application to the host organization via a
    whitelisted MCP tool, then move to waiting for their response."""
    tid = state["thread_id"]
    print(f"--- [Submit] Sending application for '{state.get('selected_program')}' | thread={tid} ---")
    try:
        res = call_mcp_tool("submit_application", {
            "program": state.get("selected_program"),
            "student_name": state.get("student_name"),
        })
        state["application_id"] = res.get("application_id")
        state["status"] = "pending_external"
        save_checkpoint(tid, "submit_application_node", state)
        return state
    except Exception as e:
        state["status"] = "failed"
        create_failure_ticket(tid, "submit_application_node", f"Submit Error: {str(e)}")
        save_checkpoint(tid, "submit_application_node", state)
        return state


def external_response_wait_node(state: dict) -> dict:
    """Node: wait for the host university/company response (the main
    external branch in this graph).

    This node can genuinely take days or weeks in production. It reads the
    latest known signal from the external party. If there's no response
    yet, the graph pauses here (checkpointed) until someone calls resume
    again once a response has arrived.
    """
    tid = state["thread_id"]
    idx = state.get("preference_index", 0)
    print(f"--- [Wait] Checking external response | thread={tid} pref_idx={idx} ---")

    signal = get_external_signal(tid, idx)
    if signal is None:
        state["status"] = "pending_external"  # still no response - stay paused here
        save_checkpoint(tid, "external_response_wait_node", state)
        print("Pausing: no response from the external party yet. Graph is in a waiting state.")
        return state

    state["external_signal"] = signal
    if signal == "approved":
        state["status"] = "external_approved"
    else:  # 'rejected' or 'timeout'
        state["status"] = "external_rejected"
        state["failure_reason"] = f"External party response: {signal}"

    save_checkpoint(tid, "external_response_wait_node", state)
    return state


def rejection_redirect_node(state: dict) -> dict:
    """Node: handles an external failure (rejection/timeout) -> redirects
    the student to a second-choice preference.

    This is the main CYCLE in the graph: it increments preference_index
    and sends the state back to lats_search_node, while fully preserving
    all already-completed data (student_name, documents_valid,
    program_choices) - none of it gets rebuilt from scratch.
    """
    tid = state["thread_id"]
    prev_idx = state.get("preference_index", 0)
    print(f"--- [Redirect] Program #{prev_idx} rejected/timed out. Redirecting... | thread={tid} ---")

    state["preference_index"] = prev_idx + 1
    state["rejected_programs"] = state.get("rejected_programs", []) + [state.get("selected_program")]
    # Student data and completed documents are preserved as-is - this is
    # the whole point of this node.
    state["status"] = "redirected"

    save_checkpoint(tid, "rejection_redirect_node", state)
    return state


def hitl_gate_node(state: dict) -> dict:
    """Node: HITL Gate - final signature on the nomination letter *or*
    financial grant approval, whichever applies, always requires direct
    Admin sign-off. Approval is always required on final placement (a
    nomination letter exists in every case), not only when requires_grant
    is True - a prior bug used to finalize grant-free programs (e.g. NUS
    Singapore) without any Admin sign-off at all."""
    tid = state["thread_id"]
    print(f"--- [HITL] Gate Node | thread={tid} ---")

    reason = (
        f"Approve nomination letter and financial grant for program: {state.get('selected_program')}"
        if state.get("requires_grant")
        else f"Approve nomination letter only (no grant) for program: {state.get('selected_program')}"
    )

    task_id = create_hitl_task(
        thread_id=tid,
        reason=reason,
        details={"program": state.get("selected_program"), "student": state.get("student_name"),
                  "requires_grant": state.get("requires_grant", False)},
        required_role="ADMIN",
    )
    state["hitl_task_id"] = task_id
    state["status"] = "paused_for_hitl"
    save_checkpoint(tid, "hitl_gate_node", state)
    print(f"Pausing: waiting on Admin approval (hitl_task_id={task_id}).")
    return state


def check_hitl_resolution_node(state: dict) -> dict:
    """Node: checked on resume - has the Admin responded to the HITL task or not yet."""
    tid = state["thread_id"]
    task = get_latest_hitl_task(tid)
    print(f"--- [HITL Check] thread={tid} task_status={task.get('status') if task else None} ---")

    if not task or task["status"] == "pending":
        state["status"] = "paused_for_hitl"  # still waiting
        save_checkpoint(tid, "check_hitl_resolution_node", state)
        return state

    if task["status"] == "approved":
        state["status"] = "finalized"
    else:  # 'rejected'
        state["status"] = "redirected"
        state["rejected_programs"] = state.get("rejected_programs", []) + [state.get("selected_program")]
        state["preference_index"] = state.get("preference_index", 0) + 1

    save_checkpoint(tid, "check_hitl_resolution_node", state)
    return state


def finalize_node(state: dict) -> dict:
    tid = state["thread_id"]
    print(f"--- [Finalize] Program secured: {state.get('selected_program')} | thread={tid} ---")
    state["status"] = "finalized"
    save_checkpoint(tid, "finalize_node", state)
    return state


# ======================================================
# Graph definition: nodes + edges (explicit, not a scattered if-chain)
# ======================================================

NODES = {
    "lats_search_node": lats_search_node,
    "constrained_react_validation_node": constrained_react_validation_node,
    "submit_application_node": submit_application_node,
    "external_response_wait_node": external_response_wait_node,
    "rejection_redirect_node": rejection_redirect_node,
    "hitl_gate_node": hitl_gate_node,
    "check_hitl_resolution_node": check_hitl_resolution_node,
    "finalize_node": finalize_node,
}

# status -> name of the node to run next. Statuses not present here are
# pause points / terminal states for the current run.
EDGES = {
    "start": "lats_search_node",
    "lats_completed": "constrained_react_validation_node",
    "validation_completed": "submit_application_node",
    "pending_external": "external_response_wait_node",
    "external_approved": "hitl_gate_node",
    "external_rejected": "rejection_redirect_node",
    "redirected": "lats_search_node",          # <-- the main CYCLE in this graph
    "paused_for_hitl": "check_hitl_resolution_node",  # only checked when resume is called again
}

# Terminal/pause states with no outgoing edge (execution stops here for the current run)
TERMINAL_OR_PAUSE_STATES = {"finalized", "failed", "no_more_options"}


def run_or_resume_graph(thread_id: str, student_email: str = "omar.k@brightpeak.edu") -> dict:
    checkpoint = load_latest_checkpoint(thread_id)
    if checkpoint:
        print(f"Resuming thread '{thread_id}' from status: {checkpoint.get('status')}")
        state = checkpoint
    else:
        print(f"Starting new graph run for thread '{thread_id}'")
        state = {
            "thread_id": thread_id,
            "student_email": student_email,
            "preference_index": 0,
            "status": "start",
        }

    steps = 0
    max_steps = 30  # extra safety net against an infinite loop in case of a bug
    while state["status"] not in TERMINAL_OR_PAUSE_STATES and steps < max_steps:
        node_name = EDGES.get(state["status"])
        if node_name is None:
            break  # a genuine stop state that isn't defined in EDGES

        prev_status = state["status"]
        state = NODES[node_name](state)
        steps += 1

        # If the node returned the same status it started with (meaning
        # it's still waiting: pending_external / paused_for_hitl), stop
        # the loop here until someone calls run_or_resume_graph again
        # after a response arrives.
        if state["status"] == prev_status and prev_status in ("pending_external", "paused_for_hitl"):
            break

        if idx := state.get("preference_index"):
            if idx >= MAX_PREFERENCE_ATTEMPTS:
                state["status"] = "no_more_options"
                state["failure_reason"] = "Exhausted all allowed redirect attempts"
                save_checkpoint(thread_id, "run_or_resume_graph", state)
                break

    return state


if __name__ == "__main__":
    result = run_or_resume_graph("thread_user_101")
    print("\nFinal/Current State:", json.dumps(result, indent=2, ensure_ascii=False))