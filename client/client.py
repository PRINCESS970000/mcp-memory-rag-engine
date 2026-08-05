from fastmcp.client import (
    Client,
    PythonStdioTransport,
    StreamableHttpTransport
)
from mcp.types import SamplingCapability
import asyncio
import os

# ======================================================
# Path to the MCP Server
# ======================================================

SERVER_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "mcp_server",
        "server.py"
    )
)
import sys

# ======================================================
# Transport Configuration
# ======================================================

if len(sys.argv) > 1:
    TRANSPORT_TYPE = sys.argv[1].lower()
else:
    TRANSPORT_TYPE = "stdio"


if TRANSPORT_TYPE == "stdio":

    transport = PythonStdioTransport(SERVER_FILE)

elif TRANSPORT_TYPE == "http":

    transport = StreamableHttpTransport(
        "http://127.0.0.1:8000/mcp"
    )

else:
    raise ValueError(
        "Transport must be either 'stdio' or 'http'."
    )


# ======================================================
# Progress Handler
# ======================================================

async def progress_handler(progress, total, message):

    percent = (progress / total) * 100

    print(f"\nProgress: {percent:.0f}%")

    if message:
        print(message)


# ======================================================
# Sampling Handler
# ======================================================

async def sampling_handler(messages, params, context):

    print("\n========== Sampling Request ==========\n")

    prompt = messages[0].content.text

    print(prompt.strip())

    print("\n========== Generating Response ==========\n")

    response = """
Overall Performance:
Excellent

Strengths:
- Strong performance in core courses.
- High grades in completed subjects.
- Consistent academic achievement.

Weaknesses:
- One course is still in progress.

Recommendation:
Continue maintaining the current performance and focus on completing the remaining courses with the same level of excellence.
"""

    return response


# ======================================================
# Create Client
# ======================================================

client = Client(
    transport,
    progress_handler=progress_handler,
    sampling_handler=sampling_handler,
    sampling_capabilities=SamplingCapability()
)


# ======================================================
# Main Function
# ======================================================

async def main():

    async with client:

        print("✅ Connected to Brightpeak MCP Server!")

        # ------------------------------------------------
        # List Tools
        # ------------------------------------------------

        tools = await client.list_tools()

        print("\n========== Available Tools ==========\n")

        for tool in tools:
            print(f"Tool Name: {tool.name}")
            print(f"Description: {tool.description}")
            print("-" * 50)

        # ------------------------------------------------
        # list_all_courses
        # ------------------------------------------------

        print("\n========== Calling list_all_courses ==========\n")

        result = await client.call_tool("list_all_courses")

        courses = result.data["courses"]

        for course in courses:
            print(f"Course ID   : {course['course_id']}")
            print(f"Title       : {course['title']}")
            print(f"Instructor  : {course['instructor_name']}")
            print(f"Credits     : {course['credits']}")
            print("-" * 40)

        # ------------------------------------------------
        # get_student_profile
        # ------------------------------------------------

        print("\n========== Calling get_student_profile ==========\n")

        result = await client.call_tool(
            "get_student_profile",
            {
                "email": "omar.k@brightpeak.edu"
            }
        )

        student = result.data["data"]

        print(f"Name  : {student['name']}")
        print(f"Email : {student['email']}")
        print(f"Role  : {student['role']}")

        print("\nCourses:")

        for course in student["enrolled_courses"]:
            print(f"Course : {course['title']}")
            print(f"Grade  : {course['grade']}")
            print(f"Status : {course['status']}")
            print("-" * 30)

        # ------------------------------------------------
        # update_student_grade
        # ------------------------------------------------

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

        # ------------------------------------------------
        # Verify Update
        # ------------------------------------------------

        print("\n========== Verify Updated Student ==========\n")

        result = await client.call_tool(
            "get_student_profile",
            {
                "email": "youssef.i@brightpeak.edu"
            }
        )

        student = result.data["data"]

        for course in student["enrolled_courses"]:
            print(course)

        # ------------------------------------------------
        # generate_academic_report
        # ------------------------------------------------

        print("\n========== Calling generate_academic_report ==========\n")

        result = await client.call_tool("generate_academic_report")

        print(result.data)

        # ------------------------------------------------
        # request_student_evaluation
        # ------------------------------------------------

        print("\n========== Calling request_student_evaluation ==========\n")

        result = await client.call_tool(
            "request_student_evaluation",
            {
                "student_id": 1
            }
        )

        evaluation = result.data["evaluation"]

        print("\n========== Student Evaluation ==========\n")
        print("=" * 60)
        print("STUDENT EVALUATION")
        print("=" * 60)
        print(evaluation.strip())
        print("=" * 60)


# ======================================================
# Run Client
# ======================================================

if __name__ == "__main__":
    asyncio.run(main())
