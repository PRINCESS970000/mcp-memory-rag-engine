
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
 
import data_access
 
app = FastAPI(title="Brightpeak Admin Platform")
 
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
 
 
@app.get("/")
def serve_dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))
 
 
# ---------------------------------------------------------------------------
# HITL endpoints
# ---------------------------------------------------------------------------
 
@app.get("/api/hitl")
def get_pending_hitl_tasks():
    return data_access.list_pending_hitl_tasks()
 
 
class HitlDecision(BaseModel):
    approved: bool
 
 
@app.post("/api/hitl/{hitl_id}/resolve")
def resolve_hitl(hitl_id: int, decision: HitlDecision):
    try:
        return data_access.resolve_hitl_and_resume(hitl_id, decision.approved)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
 
 
# ---------------------------------------------------------------------------
# Ticket endpoints
# ---------------------------------------------------------------------------
 
@app.get("/api/tickets")
def get_open_tickets():
    return data_access.list_open_tickets()
 
 
@app.post("/api/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int):
    try:
        return data_access.resolve_ticket_and_resume(ticket_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))