"""
platform/user/backend/main.py

Real backend for the user platform: agent switcher (memory/RAG+planning
chat vs. the 3 state-graph agents) + admin-lite panel for HITL tasks and
tickets, so the crash/ticket/HITL demo can be shown from one UI instead
of raw terminal scripts.

Nothing here is mocked -- every endpoint calls the real modules built
across state_graph/, state_graph/tickets/, and agent/loop.py.

Run:
    cd platform/user/backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8010
Then open http://127.0.0.1:8010/ (serves the frontend too).
"""

import sys
import uuid
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- memory/RAG + planning agent (single unified entry point) ---
from agent.loop import handle_message
from memory.short_term import ShortTermMemory  # same class agent/loop.py uses

# --- state graphs ---
import state_graph.graph_1_study_abroad as graph_study_abroad
import state_graph.graph_2_scholarship as graph_scholarship
import state_graph.graph_3_internship as graph_internship
from state_graph.base import (
    get_db_connection,
    list_open_failure_tickets,
    resolve_hitl_task,
)
from state_graph.tickets.resolve import resolve_ticket_and_resume

app = FastAPI(title="BrightPeak Platform — User")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store for the chat agent (fine for a demo; a real
# deployment would key this off a persisted session table instead).
_SESSIONS: dict[str, ShortTermMemory] = {}


def _get_session(session_id: str, student_id: int) -> ShortTermMemory:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = ShortTermMemory(session_id=session_id, student_id=student_id)
    return _SESSIONS[session_id]


AGENTS = [
    {"id": "memory_rag", "name": "Memory / RAG / Planning (chat)", "type": "chat"},
    {"id": "study_abroad", "name": "Study Abroad Graph", "type": "graph"},
    {"id": "scholarship", "name": "Scholarship Graph", "type": "graph"},
    {"id": "internship", "name": "Internship Graph", "type": "graph"},
]


@app.get("/api/agents")
def list_agents():
    return AGENTS


# ---------------------------------------------------------------------------
# Chat agent (memory/RAG/planning)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    student_id: int
    message: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    stm = _get_session(req.session_id, req.student_id)
    result = handle_message(stm, req.student_id, req.message)
    return result


# ---------------------------------------------------------------------------
# State-graph agents: start / resume
# ---------------------------------------------------------------------------

class GraphStartRequest(BaseModel):
    graph: str  # "study_abroad" | "scholarship" | "internship"
    student_id: int
    # internship
    target_role_title: Optional[str] = None
    # scholarship
    requested_amount: Optional[float] = None
    sponsor_name: Optional[str] = None
    total_installments: int = 3
    max_appeals: int = 2
    # study_abroad
    student_email: Optional[str] = None


class GraphResumeRequest(BaseModel):
    graph: str
    thread_id: str


@app.post("/api/graph/start")
async def graph_start(req: GraphStartRequest):
    if req.graph == "internship":
        if not req.target_role_title:
            raise HTTPException(400, "target_role_title is required for internship graph")
        state = await graph_internship.start_new_application(req.student_id, req.target_role_title)
        return {"thread_id": state["thread_id"], "state": state}

    if req.graph == "scholarship":
        if req.requested_amount is None:
            raise HTTPException(400, "requested_amount is required for scholarship graph")
        state = await graph_scholarship.start_new_application(
            student_id=req.student_id,
            requested_amount=req.requested_amount,
            sponsor_name=req.sponsor_name,
            total_installments=req.total_installments,
            max_appeals=req.max_appeals,
        )
        return {"thread_id": state["thread_id"], "state": state}

    if req.graph == "study_abroad":
        # graph_1 has no separate start_new_application: run_or_resume_graph
        # self-initializes when it finds no checkpoint for the thread_id.
        # No shared thread_id prefix convention exists for this graph yet
        # (flagged separately) -- using our own clean one here.
        thread_id = f"study_abroad-{req.student_id}-{uuid.uuid4().hex[:6]}"
        email = req.student_email or "omar.k@brightpeak.edu"
        state = graph_study_abroad.run_or_resume_graph(thread_id, email)
        return {"thread_id": thread_id, "state": state}

    raise HTTPException(400, f"Unknown graph '{req.graph}'")


@app.post("/api/graph/resume")
async def graph_resume(req: GraphResumeRequest):
    if req.graph == "internship":
        state = await graph_internship.run_or_resume_graph(req.thread_id)
    elif req.graph == "scholarship":
        state = await graph_scholarship.run_or_resume_graph(req.thread_id)
    elif req.graph == "study_abroad":
        state = graph_study_abroad.run_or_resume_graph(req.thread_id)
    else:
        raise HTTPException(400, f"Unknown graph '{req.graph}'")
    return {"thread_id": req.thread_id, "state": state}


class ExternalSignalRequest(BaseModel):
    graph: str
    thread_id: str
    # study_abroad
    preference_index: Optional[int] = None
    signal: str  # 'approved' | 'rejected' | 'timeout' | 'completed' | 'accepted'
    signal_type: Optional[str] = None  # internship only: 'course_completion' | 'company_response'


@app.post("/api/graph/external-signal")
def set_external_signal(req: ExternalSignalRequest):
    """
    Simulates a real-world external response arriving (company/university
    reply, course completion) -- lets the demo/video trigger the branch
    without waiting for a real webhook.
    """
    if req.graph == "study_abroad":
        if req.preference_index is None:
            raise HTTPException(400, "preference_index is required for study_abroad")
        graph_study_abroad.set_external_signal(req.thread_id, req.preference_index, req.signal)
    elif req.graph == "internship":
        if not req.signal_type:
            raise HTTPException(400, "signal_type is required for internship")
        graph_internship.set_external_signal(req.thread_id, req.signal_type, req.signal)
    else:
        raise HTTPException(400, f"'{req.graph}' has no external-signal simulation endpoint")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# HITL tasks (admin-lite panel)
# ---------------------------------------------------------------------------

@app.get("/api/hitl/pending")
def list_pending_hitl():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hitl_tasks WHERE status = 'pending' ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


class HitlDecisionRequest(BaseModel):
    task_id: int
    decision: str  # 'approved' | 'rejected'
    graph: str     # which graph this task's thread belongs to, so we know how to resume
    thread_id: str


@app.post("/api/hitl/decide")
async def decide_hitl(req: HitlDecisionRequest):
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")

    resolve_hitl_task(req.task_id, req.decision)

    if req.graph == "internship":
        state = await graph_internship.run_or_resume_graph(req.thread_id)
    elif req.graph == "scholarship":
        state = await graph_scholarship.run_or_resume_graph(req.thread_id)
    elif req.graph == "study_abroad":
        state = graph_study_abroad.run_or_resume_graph(req.thread_id)
    else:
        raise HTTPException(400, f"Unknown graph '{req.graph}'")

    return {"thread_id": req.thread_id, "state": state}


# ---------------------------------------------------------------------------
# Failure tickets (includes stagnation tickets from state_graph/tickets/)
# ---------------------------------------------------------------------------

@app.get("/api/tickets/open")
def open_tickets():
    return list_open_failure_tickets()


class TicketResolveRequest(BaseModel):
    ticket_id: int


@app.post("/api/tickets/resolve")
async def resolve_ticket(req: TicketResolveRequest):
    state = await resolve_ticket_and_resume(req.ticket_id)
    return {"state": state}


# ---------------------------------------------------------------------------
# Serve the frontend
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")