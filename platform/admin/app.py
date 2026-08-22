from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import data_access
import rag_admin
 
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
async def resolve_hitl(hitl_id: int, decision: HitlDecision):
    try:
        return await data_access.resolve_hitl_and_resume(hitl_id, decision.approved)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
 
 
# ---------------------------------------------------------------------------
# Ticket endpoints
# ---------------------------------------------------------------------------
 
@app.get("/api/tickets")
def get_open_tickets():
    return data_access.list_open_tickets()
 
 
@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int):
    try:
        return await data_access.resolve_ticket_and_resume(ticket_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
 
 
# ---------------------------------------------------------------------------
# Tool management endpoints (runtime, reaches the live MCP server)
# ---------------------------------------------------------------------------
 
@app.get("/api/tools")
def get_tools():
    return tools_and_rag_access.list_tools()
 
 
@app.post("/api/tools/{tool_name}/disable")
def disable_tool(tool_name: str):
    return tools_and_rag_access.disable_tool(tool_name)
 
 
@app.post("/api/tools/{tool_name}/enable")
def enable_tool(tool_name: str):
    return tools_and_rag_access.enable_tool(tool_name)
 
 
# ---------------------------------------------------------------------------
# RAG document management endpoints
# ---------------------------------------------------------------------------
 
@app.get("/api/rag/documents")
def get_rag_documents():
    return tools_and_rag_access.list_rag_documents()
 
 
class RagDocument(BaseModel):
    id: str
    text: str
    policy_type: str
    section_title: str = ""
 
 
@app.post("/api/rag/documents")
def add_rag_document(doc: RagDocument):
    return tools_and_rag_access.add_rag_document(doc.id, doc.text, doc.policy_type, doc.section_title)
 
 
@app.delete("/api/rag/documents/{doc_id}")
def delete_rag_document(doc_id: str):
    return tools_and_rag_access.delete_rag_document(doc_id)
 
 
# ---------------------------------------------------------------------------
# MCP Tools management
# ---------------------------------------------------------------------------
 
@app.get("/api/tools")
def get_mcp_tools():
    return data_access.list_mcp_tools()
 
 
@app.post("/api/tools/{tool_name}/toggle")
def toggle_tool(tool_name: str):
    try:
        return data_access.toggle_mcp_tool(tool_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
 
 
# ---------------------------------------------------------------------------
# RAG documents management
# ---------------------------------------------------------------------------
 
import rag_admin
 
 
class NewDocument(BaseModel):
    text: str
    policy_type: str
    section_title: str = ""
 
 
@app.get("/api/rag/documents")
def get_rag_documents():
    return rag_admin.list_documents()
 
 
@app.post("/api/rag/documents")
def add_rag_document(doc: NewDocument):
    return rag_admin.add_document(doc.text, doc.policy_type, doc.section_title)
 
 
@app.delete("/api/rag/documents/{doc_id}")
def delete_rag_document(doc_id: str):
    rag_admin.delete_document(doc_id)
    return {"deleted": doc_id}