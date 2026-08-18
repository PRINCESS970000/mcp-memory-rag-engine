import os
import sys
import asyncio
import uuid
from fastmcp.client import Client, PythonStdioTransport, StreamableHttpTransport
from mcp.types import SamplingCapability

# ======================================================
# Config & Paths
# ======================================================

SERVER_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "mcp_server",
        "server.py"
    )
)

if len(sys.argv) > 1:
    TRANSPORT_TYPE = sys.argv[1].lower()
else:
    TRANSPORT_TYPE = "stdio"


def get_transport(transport_type: str = TRANSPORT_TYPE):
    if transport_type == "stdio":
        return PythonStdioTransport(SERVER_FILE)
    elif transport_type == "http":
        return StreamableHttpTransport("http://127.0.0.1:8000/mcp")
    else:
        raise ValueError("Transport must be either 'stdio' or 'http'.")


# ======================================================
# Handlers
# ======================================================

async def progress_handler(progress, total, message):
    percent = (progress / total) * 100
    if message:
        print(f"[MCP Progress {percent:.0f}%] {message}")


async def sampling_handler(messages, params, context):
    return """
Overall Performance: Excellent
Recommendation: Approved for exchange program requirements.
"""


# ======================================================
# Main Client Instance
# ======================================================

client = Client(
    get_transport(),
    progress_handler=progress_handler,
    sampling_handler=sampling_handler,
    sampling_capabilities=SamplingCapability()
)


# ======================================================
# State Graph Helper Invokers
# ======================================================

async def call_mcp_tool_async(tool_name: str, arguments: dict = None, transport_type: str = TRANSPORT_TYPE):
    """استدعاء أداة MCP بشكل Async لاستخدامها داخل الـ State Graph"""
    if arguments is None:
        arguments = {}

    transport = get_transport(transport_type)
    async_client = Client(
        transport,
        progress_handler=progress_handler,
        sampling_handler=sampling_handler,
        sampling_capabilities=SamplingCapability()
    )

    async with async_client:
        result = await async_client.call_tool(tool_name, arguments)
        return result.data


def call_mcp_tool(tool_name: str, arguments: dict = None, transport_type: str = TRANSPORT_TYPE):
    """استدعاء أداة MCP بشكل Sync لاستخدامها داخل الـ Nodes المباشرة"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(call_mcp_tool_async(tool_name, arguments, transport_type))
    else:
        return asyncio.run(call_mcp_tool_async(tool_name, arguments, transport_type))


# ======================================================
# Main Script Execution (Standalone Test)
# ======================================================

async def main():
    async with client:
        print("✅ Connected to Brightpeak MCP Server!")

        # 1. List Tools
        tools = await client.list_tools()
        print("\n========== Available Tools ==========\n")
        for tool in tools:
            print(f"Tool Name: {tool.name}")
            print(f"Description: {tool.description}")
            print("-" * 50)

        # 2. list_all_courses
        print("\n========== Calling list_all_courses ==========\n")
        result = await client.call_tool("list_all_courses")
        courses = result.data.get("courses", [])
        for course in courses:
            print(f"Course ID   : {course['course_id']}")
            print(f"Title       : {course['title']}")
            print(f"Instructor  : {course['instructor_name']}")
            print(f"Credits     : {course['credits']}")
            print("-" * 40)

        # 3. get_student_profile
        print("\n========== Calling get_student_profile ==========\n")
        result = await client.call_tool(
            "get_student_profile",
            {"email": "omar.k@brightpeak.edu"}
        )
        student = result.data.get("data", {})
        print(f"Name  : {student.get('name')}")
        print(f"Email : {student.get('email')}")
        print(f"Role  : {student.get('role')}")
        print("\nCourses:")
        for course in student.get("enrolled_courses", []):
            print(f"Course : {course['title']}")
            print(f"Grade  : {course['grade']}")
            print(f"Status : {course['status']}")
            print("-" * 30)

        # 4. update_student_grade
        print("\n========== Calling update_student_grade ==========\n")
        result = await client.call_tool(
            "update_student_grade",
            {
                "student_id": 4,
                "course_id": 3,
                "new_grade": 97.5,
                "requester_role": "INSTRUCTOR"
            }
        )
        print(result.data)

        # 5. Verify Update
        print("\n========== Verify Updated Student ==========\n")
        result = await client.call_tool(
            "get_student_profile",
            {"email": "youssef.i@brightpeak.edu"}
        )
        student = result.data.get("data", {})
        for course in student.get("enrolled_courses", []):
            print(course)

        # 6. generate_academic_report
        print("\n========== Calling generate_academic_report ==========\n")
        result = await client.call_tool("generate_academic_report")
        print(result.data)

        # 7. request_student_evaluation
        print("\n========== Calling request_student_evaluation ==========\n")
        session_id = str(uuid.uuid4())
        result = await client.call_tool(
            "request_student_evaluation",
            {
                "student_id": 1,
                "session_id": session_id
            }
        )
        evaluation = result.data.get("evaluation", "")
        print("\n========== Student Evaluation ==========\n")
        print("=" * 60)
        print("STUDENT EVALUATION")
        print("=" * 60)
        print(evaluation.strip())
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())