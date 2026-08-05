import sqlite3
import os
import re
import time
import asyncio
import sys
from fastmcp import FastMCP, Context


mcp = FastMCP("Brightpeak Academy Server")


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "brightpeak.db")

# Rolling buffer: max number of messages kept per session.
# Once a session exceeds this, the oldest messages are deleted.
MAX_HISTORY_PER_SESSION = 20


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_messages_table():
    """Creates the messages table if it doesn't already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            student_id INTEGER,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session
        ON messages (session_id, created_at)
    """)
    conn.commit()
    conn.close()


# Ensure the table exists as soon as the module loads.
init_messages_table()


@mcp.tool()
def get_student_profile(email: str) -> dict:
    # 1. Input Validation:
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        return {"status": "error", "message": "Invalid email format."}

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2. Logic Validation:
    cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        return {"status": "error", "message": f"Student with email '{email}' not found."}

    # 3. Fetching Enrolled Courses and Grades
    query = """
        SELECT c.title, e.grade, e.status
        FROM enrollments e
        JOIN courses c ON e.course_id = c.course_id
        WHERE e.student_id = ?
    """
    cursor.execute(query, (student["student_id"],))
    courses = cursor.fetchall()
    conn.close()

    return {
        "status": "success",
        "data": {
            "student_id": student["student_id"],
            "name": student["name"],
            "email": student["email"],
            "role": student["role"],
            "enrolled_courses": [dict(row) for row in courses]
        }
    }


@mcp.tool()
def list_all_courses() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.course_id, c.title, c.credits, i.name as instructor_name
        FROM courses c
        LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return {
        "status": "success",
        "courses": [dict(row) for row in rows]
    }


@mcp.tool()
def enroll_student(student_id: int, course_id: int) -> dict:
    # 1. Input Validation:
    if student_id <= 0 or course_id <= 0:
        return {"status": "error", "message": "Student ID and Course ID must be positive integers."}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 2. Logic Validation
        cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
        if not cursor.fetchone():
            return {"status": "error", "message": f"Student ID {student_id} does not exist."}

        # 3. Logic Validation:
        cursor.execute("SELECT course_id FROM courses WHERE course_id = ?", (course_id,))
        if not cursor.fetchone():
            return {"status": "error", "message": f"Course ID {course_id} does not exist."}

        # 4. Duplicate Check:
        cursor.execute(
            "SELECT enrollment_id FROM enrollments WHERE student_id = ? AND course_id = ?",
            (student_id, course_id)
        )
        if cursor.fetchone():
            return {"status": "error", "message": "Student is already enrolled in this course."}

        # 5. Insert Enrollment Record
        cursor.execute(
            "INSERT INTO enrollments (student_id, course_id, status) VALUES (?, ?, 'ENROLLED')",
            (student_id, course_id)
        )
        conn.commit()
        return {"status": "success", "message": f"Successfully enrolled student {student_id} in course {course_id}."}

    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()


@mcp.tool(
    name="update_student_grade",
    description="Updates a student's grade for a specific course. Requires INSTRUCTOR or ADMIN role and strict input validation."
)
def update_student_grade(student_id: int, course_id: int, new_grade: float, requester_role: str) -> dict:
    # 1. Authorization Check
    allowed_roles = ["INSTRUCTOR", "ADMIN"]
    if requester_role not in allowed_roles:
        return {
            "status": "error",
            "message": f"Authorization denied. Role '{requester_role}' is not permitted to modify grades."
        }

    # 2. Server-side Validation
    if not (0.0 <= new_grade <= 100.0):
        return {
            "status": "error",
            "message": "Invalid grade. Grade must be between 0.0 and 100.0."
        }

    if student_id <= 0 or course_id <= 0:
        return {
            "status": "error",
            "message": "Student ID and Course ID must be positive integers."
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 3. Check if enrollment exists
        cursor.execute(
            "SELECT enrollment_id FROM enrollments WHERE student_id = ? AND course_id = ?",
            (student_id, course_id)
        )
        enrollment = cursor.fetchone()

        if not enrollment:
            return {
                "status": "error",
                "message": f"No active enrollment found for Student ID {student_id} in Course ID {course_id}."
            }

        # 4. Perform Update
        cursor.execute(
            "UPDATE enrollments SET grade = ?, status = 'COMPLETED' WHERE student_id = ? AND course_id = ?",
            (new_grade, student_id, course_id)
        )
        conn.commit()

        return {
            "status": "success",
            "message": f"Successfully updated grade for student {student_id} in course {course_id} to {new_grade}."
        }

    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()


@mcp.tool(
    name="generate_academic_report",
    description="Generates a comprehensive academic report for all courses and students."
)
async def generate_academic_report(ctx: Context) -> dict:
    await ctx.report_progress(progress=0, total=100)

    await asyncio.sleep(1)
    await ctx.report_progress(30, 100, "Collecting student records...")

    await asyncio.sleep(1)
    await ctx.report_progress(70, 100, "Analyzing grades...")

    await asyncio.sleep(1)
    await ctx.report_progress(100, 100, "Generating final report...")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as student_count FROM students")
    student_count = cursor.fetchone()["student_count"]

    cursor.execute("SELECT COUNT(*) as course_count FROM courses")
    course_count = cursor.fetchone()["course_count"]

    conn.close()

    return {
        "status": "success",
        "message": "Academic report generated successfully with progress tracking.",
        "report_summary": {
            "total_students": student_count,
            "total_courses": course_count,
            "status": "Completed all evaluation steps"
        }
    }


# ---------------------------------------------------------------------------
# Chat history / rolling buffer
# ---------------------------------------------------------------------------

@mcp.tool(
    name="store_message",
    description="Stores a chat message under a session_id and applies a rolling buffer, "
                "keeping only the most recent messages per session."
)
def store_message(session_id: str, role: str, content: str, student_id: int = None) -> dict:
    # 1. Input Validation
    if not session_id or not session_id.strip():
        return {"status": "error", "message": "session_id is required."}

    allowed_roles = ["user", "assistant", "system"]
    if role not in allowed_roles:
        return {"status": "error", "message": f"role must be one of {allowed_roles}."}

    if not content or not content.strip():
        return {"status": "error", "message": "content cannot be empty."}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 2. Insert the new message
        cursor.execute(
            "INSERT INTO messages (session_id, student_id, role, content) VALUES (?, ?, ?, ?)",
            (session_id, student_id, role, content)
        )
        conn.commit()

        # 3. Rolling buffer: trim oldest messages beyond the max per session
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,)
        )
        total = cursor.fetchone()["cnt"]

        if total > MAX_HISTORY_PER_SESSION:
            excess = total - MAX_HISTORY_PER_SESSION
            cursor.execute(
                """
                DELETE FROM messages
                WHERE message_id IN (
                    SELECT message_id FROM messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (session_id, excess)
            )
            conn.commit()

        return {"status": "success", "message": "Message stored.", "session_id": session_id}

    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()


@mcp.tool(
    name="get_chat_history",
    description="Returns the stored chat history for a session as an ordered list of "
                "messages (role/content), ready to use as MCP sampling input."
)
def get_chat_history(session_id: str, limit: int = MAX_HISTORY_PER_SESSION) -> dict:
    if not session_id or not session_id.strip():
        return {"status": "error", "message": "session_id is required."}

    if limit <= 0:
        return {"status": "error", "message": "limit must be a positive integer."}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content, created_at FROM messages
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()

    # Reverse back to chronological order (oldest -> newest)
    rows = list(reversed(rows))

    messages = [{"role": row["role"], "content": row["content"]} for row in rows]

    return {
        "status": "success",
        "session_id": session_id,
        "count": len(messages),
        "messages": messages
    }


@mcp.tool(
    name="clear_chat_history",
    description="Deletes all stored messages for a given session_id."
)
def clear_chat_history(session_id: str) -> dict:
    if not session_id or not session_id.strip():
        return {"status": "error", "message": "session_id is required."}

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    return {"status": "success", "message": f"Deleted {deleted} message(s) for session '{session_id}'."}


@mcp.tool(
    name="request_student_evaluation",
    description="Requests the client model to evaluate a student's academic standing based on "
                "their grades using sampling, with conversation history kept in a session-based "
                "rolling buffer."
)
async def request_student_evaluation(student_id: int, session_id: str, ctx: Context) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get student information
    cursor.execute(
        "SELECT name, email FROM students WHERE student_id = ?",
        (student_id,)
    )
    student = cursor.fetchone()

    if not student:
        conn.close()
        return {
            "status": "error",
            "message": f"Student ID {student_id} not found."
        }

    # Get enrolled courses
    query = """
         SELECT c.title, e.grade, e.status
         FROM enrollments e
         JOIN courses c ON e.course_id = c.course_id
         WHERE e.student_id = ?
     """
    cursor.execute(query, (student_id,))
    courses = cursor.fetchall()
    conn.close()

    # Build the evaluation request as a message
    course_details = ""
    for course in courses:
        course_details += (
            f"- {course['title']}\n"
            f"  Grade : {course['grade']}\n"
            f"  Status: {course['status']}\n\n"
        )

    user_prompt = f"""
    You are an academic advisor.

    Evaluate the academic performance of the following student.

    Student Name:
    {student['name']}

    Courses:
    {course_details}

    Please provide:

    1. Overall Performance
    2. Strengths
    3. Weaknesses
    4. Recommendation

    Keep the response concise and professional.
    """

    # 1. Persist this turn in the session's rolling buffer
    store_message(session_id=session_id, role="user", content=user_prompt, student_id=student_id)

    # 2. Pull the session's history back out as a proper list of messages
    history = get_chat_history(session_id=session_id)
    messages_list = history["messages"]

    # 3. Ask the client model using the full message list (not a single string)
    response = await ctx.sample(
        messages=messages_list,
        max_tokens=150
    )

    # 4. Persist the assistant's reply too, so the next call continues the same session
    store_message(session_id=session_id, role="assistant", content=response.text, student_id=student_id)

    return {
        "status": "success",
        "session_id": session_id,
        "evaluation": response.text
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        mcp.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=8000
        )
    else:
        mcp.run(
            transport="stdio"
        )