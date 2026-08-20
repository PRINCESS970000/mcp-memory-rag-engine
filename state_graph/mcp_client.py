import os
from fastmcp import Client
 
SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
 
# الأدوات المصرح للـ scholarship graph يستخدمها -- أي حاجة تانية ممنوعة
ALLOWED_TOOLS = {
    "check_scholarship_eligibility",
    "submit_scholarship_application",
    "update_application_state",
    "disburse_installment",
}
 
 
async def call_mcp_tool(tool_name: str, **kwargs) -> dict:
    """
    بيفتح اتصال stdio بسيرفر الـ MCP الحقيقي، وينفذ أداة واحدة، ويقفل.
    لو الأداة مش في ALLOWED_TOOLS بيرفض من غير ما يوصل للسيرفر أصلًا --
    ده تطبيق فعلي لـ "constrained" ReAct مش مجرد تسمية.
    """
    if tool_name not in ALLOWED_TOOLS:
        return {
            "status": "error",
            "message": f"الأداة '{tool_name}' مش مصرح بيها لـ scholarship graph.",
        }
 
    async with Client(SERVER_SCRIPT) as client:
        result = await client.call_tool(tool_name, kwargs)
        # fastmcp بيرجع محتوى منظم؛ بنسحب أول نتيجة JSON منه
        return result.data if hasattr(result, "data") else result