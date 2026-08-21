"""
state_graph/mcp_client.py

طبقة رفيعة بتخلي الـ graph يستدعي أدوات MCP الحقيقية بدل ما يلمس
الـ database مباشرة (Constrained ReAct فعلي: أدوات محددة سلفًا بس).
"""

import os
from fastmcp import Client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")

ALLOWED_TOOLS = {
    "submit_graduation_application",
    "get_academic_status",
    "get_financial_status",
    "get_library_status",
    "get_required_documents",
    "update_graduation_state",
}


async def call_mcp_tool(tool_name: str, **kwargs) -> dict:
    if tool_name not in ALLOWED_TOOLS:
        return {"status": "error", "message": f"الأداة '{tool_name}' مش مصرح بيها لـ graduation graph."}

    async with Client(SERVER_SCRIPT) as client:
        result = await client.call_tool(tool_name, kwargs)
        return result.data if hasattr(result, "data") else result