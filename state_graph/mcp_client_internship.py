import os
from fastmcp import Client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")

# الأدوات المصرح للـ internship graph يستخدمها -- أي حاجة تانية ممنوعة
ALLOWED_TOOLS = {
    "get_role_requirements",
    "check_prerequisites",
    "check_internship_readiness",
    "submit_internship_application",
    "update_internship_application_state",
}


async def call_mcp_tool(tool_name: str, **kwargs) -> dict:
    """
    بيفتح اتصال stdio بسيرفر الـ MCP الحقيقي، وينفذ أداة واحدة، ويقفل.
    لو الأداة مش في ALLOWED_TOOLS بيرفض من غير ما يوصل للسيرفر أصلًا.
    """
    if tool_name not in ALLOWED_TOOLS:
        return {
            "status": "error",
            "message": f"الأداة '{tool_name}' مش مصرح بيها لـ internship graph.",
        }

    async with Client(SERVER_SCRIPT) as client:
        result = await client.call_tool(tool_name, kwargs)
        return result.data if hasattr(result, "data") else result