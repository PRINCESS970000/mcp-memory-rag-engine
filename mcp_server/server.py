import sqlite3
import os
import re
import sys
import asyncio
from fastmcp import FastMCP, Context

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from state_graph.base import init_checkpointing_tables

mcp = FastMCP("Brightpeak Academy Server")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "brightpeak.db"))

# Rolling buffer: max number of messages kept per session.
MAX_HISTORY_PER_SESSION = 20


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

import graduation_tools
graduation_tools.register(mcp, get_db_connection)



def init_messages_table():
    """Creates operational tables only. Infrastructure tables (checkpoints,
    hitl_tasks, failure_tickets) live in state_graph/checkpointing/base.py
    and MUST NOT be redefined here - see Issue #<ضيف رقم الـ issue هنا>:
    كانت السكيما القديمة هنا بتتصادم مع الطبقة المشتركة وتكسر save_checkpoint
    بـ 'OperationalError: table checkpoints has no column named state_json'
    لو السيرفر اشتغل واعمل init قبل أي graph."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Chat Messages Table (خاص بالسيرفر ده فقط - مش infra مشتركة)
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

    # جداول checkpoints / hitl_tasks / failure_tickets بتتعمل من الطبقة
    # المشتركة فقط - نفس ملف DB_PATH بالظبط، بدون أي تعريف محلي هنا.
    init_checkpointing_tables()


# Ensure tables exist as soon as the module loads.
init_messages_table()


# ======================================================
# Core Academic Tools
# ======================================================

@mcp.tool()
def get_student_profile(email: str) -> dict:
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        return {"status": "error", "message": "Invalid email format."}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        return {"status": "error", "message": f"Student with email '{email}' not found."}

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
def get_path_planning_data(student_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = cursor.fetchone()
    if not student:
        conn.close()
        return {"status": "error", "message": f"Student {student_id} not found."}

    cursor.execute("""
        SELECT course_id, title, instructor_id, credits, price, weekly_hours,
               duration_weeks, start_date, end_date, difficulty, skill_tags
        FROM courses
    """)
    courses = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT course_id, prerequisite_course_id
        FROM course_prerequisites
    """)
    prerequisites = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT course_id FROM enrollments
        WHERE student_id = ? AND status = 'COMPLETED'
    """, (student_id,))
    completed_course_ids = [row["course_id"] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT goal_id, target_role_id, weekly_hours_available, budget, target_date
        FROM learning_goals
        WHERE student_id = ?
        ORDER BY goal_id DESC LIMIT 1
    """, (student_id,))
    goal_row = cursor.fetchone()
    learning_goal = dict(goal_row) if goal_row else None

    required_skills = []
    if learning_goal:
        cursor.execute("""
            SELECT skill_tag FROM role_required_skills
            WHERE role_id = ?
        """, (learning_goal["target_role_id"],))
        required_skills = [row["skill_tag"] for row in cursor.fetchall()]

    conn.close()

    return {
        "status": "success",
        "data": {
            "student_id": student_id,
            "courses": courses,
            "prerequisites": prerequisites,
            "completed_course_ids": completed_course_ids,
            "learning_goal": learning_goal,
            "required_skills": required_skills,
        }
    }


@mcp.tool()
def enroll_student(student_id: int, course_id: int) -> dict:
    if student_id <= 0 or course_id <= 0:
        return {"status": "error", "message": "Student ID and Course ID must be positive integers."}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
        if not cursor.fetchone():
            return {"status": "error", "message": f"Student ID {student_id} does not exist."}

        cursor.execute("SELECT course_id FROM courses WHERE course_id = ?", (course_id,))
        if not cursor.fetchone():
            return {"status": "error", "message": f"Course ID {course_id} does not exist."}

        cursor.execute(
            "SELECT enrollment_id FROM enrollments WHERE student_id = ? AND course_id = ?",
            (student_id, course_id)
        )
        if cursor.fetchone():
            return {"status": "error", "message": "Student is already enrolled in this course."}

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
    description="Updates a student's grade for a specific course. Requires INSTRUCTOR or ADMIN role, verified server-side against the requester's own record - never trusted from client input."
)
def update_student_grade(student_id: int, course_id: int, new_grade: float, requester_email: str) -> dict:
    """
    ملاحظة أمان مهمة (كانت الملاحظة القديمة في التقييم):
    قبل كده كانت الدالة بتاخد `requester_role` كـ string مباشر من الكلاينت
    وتثق فيه - أي حد كان يقدر يبعت requester_role="ADMIN" ويعدّي الفحص من
    غير أي تحقق حقيقي. دلوقتي بناخد `requester_email` بس، ونجيب الـ role
    الحقيقي بتاعه من جدول students في السيرفر نفسه - العميل مبقاش يقدر
    يتحكم في الصلاحية اللي بيتفحص بيها.
    """
    allowed_roles = ["INSTRUCTOR", "ADMIN"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT role FROM students WHERE email = ?", (requester_email,))
        requester = cursor.fetchone()

        if not requester:
            return {
                "status": "error",
                "message": f"Requester '{requester_email}' not found. Authorization denied."
            }

        requester_role = requester["role"]
        if requester_role not in allowed_roles:
            return {
                "status": "error",
                "message": f"Authorization denied. Role '{requester_role}' is not permitted to modify grades."
            }

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



@mcp.tool(
    name="get_role_requirements",
    description="Returns the skill tags required for a target job role (e.g. 'Data Scientist'), "
                "used to drive gap analysis against a student's completed courses."
)
def get_role_requirements(role_title: str) -> dict:
    if not role_title or not role_title.strip():
        return {"status": "error", "message": "role_title is required."}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT role_id, title FROM job_roles WHERE title = ?", (role_title,))
    role = cursor.fetchone()

    if not role:
        conn.close()
        return {"status": "error", "message": f"No job role found matching '{role_title}'."}

    cursor.execute(
        "SELECT skill_tag FROM role_required_skills WHERE role_id = ?",
        (role["role_id"],)
    )
    skills = [row["skill_tag"] for row in cursor.fetchall()]
    conn.close()

    return {
        "status": "success",
        "data": {
            "role_id": role["role_id"],
            "title": role["title"],
            "required_skills": skills
        }
    }


@mcp.tool(
    name="search_courses",
    description="Searches courses by required skill tags and optional budget/weekly-hours/start-date "
                "constraints. Returns candidate courses for the planning agent to sequence."
)
def search_courses(
    skill_tags: list = None,
    max_price: float = None,
    max_weekly_hours: float = None,
    after_date: str = None
) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM courses WHERE 1=1"
    params = []

    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)

    if max_weekly_hours is not None:
        query += " AND weekly_hours <= ?"
        params.append(max_weekly_hours)

    if after_date is not None:
        query += " AND start_date >= ?"
        params.append(after_date)

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if skill_tags:
        wanted = set(skill_tags)
        rows = [
            r for r in rows
            if wanted & set((r.get("skill_tags") or "").split(","))
        ]

    return {"status": "success", "count": len(rows), "courses": rows}


@mcp.tool(
    name="check_prerequisites",
    description="Checks whether a student has completed all prerequisite courses for a given course. "
                "This is the grounded check used before a course can be scheduled — it reads real "
                "enrollment status, it does not ask the model."
)
def check_prerequisites(student_id: int, course_id: int) -> dict:
    if student_id <= 0 or course_id <= 0:
        return {"status": "error", "message": "student_id and course_id must be positive integers."}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT prerequisite_course_id FROM course_prerequisites WHERE course_id = ?",
        (course_id,)
    )
    required = [row["prerequisite_course_id"] for row in cursor.fetchall()]

    if not required:
        conn.close()
        return {"status": "success", "eligible": True, "missing_prerequisites": []}

    cursor.execute(
        "SELECT course_id FROM enrollments WHERE student_id = ? AND status = 'COMPLETED'",
        (student_id,)
    )
    completed = {row["course_id"] for row in cursor.fetchall()}
    conn.close()

    missing = [c for c in required if c not in completed]

    return {
        "status": "success",
        "eligible": len(missing) == 0,
        "missing_prerequisites": missing
    }


@mcp.tool(
    name="save_learning_goal",
    description="Records a student's active learning-path request: target role, weekly hours "
                "available, and budget. Called once per planning session before decomposition starts."
)
def save_learning_goal(
    student_id: int,
    target_role_title: str,
    weekly_hours_available: float,
    budget: float,
    target_date: str = None
) -> dict:
    if student_id <= 0:
        return {"status": "error", "message": "student_id must be a positive integer."}

    if weekly_hours_available <= 0:
        return {"status": "error", "message": "weekly_hours_available must be greater than 0."}

    if budget < 0:
        return {"status": "error", "message": "budget cannot be negative."}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT role_id FROM job_roles WHERE title = ?", (target_role_title,))
    role = cursor.fetchone()
    if not role:
        conn.close()
        return {"status": "error", "message": f"No job role found matching '{target_role_title}'."}

    cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": f"Student ID {student_id} does not exist."}

    try:
        cursor.execute(
            """INSERT INTO learning_goals
               (student_id, target_role_id, weekly_hours_available, budget, target_date)
               VALUES (?, ?, ?, ?, ?)""",
            (student_id, role["role_id"], weekly_hours_available, budget, target_date)
        )
        conn.commit()
        return {"status": "success", "goal_id": cursor.lastrowid}
    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Chat history / rolling buffer
# ---------------------------------------------------------------------------


@mcp.tool(
    name="store_message",
    description="Stores a chat message under a session_id and applies a rolling buffer."
)
def store_message(session_id: str, role: str, content: str, student_id: int = None) -> dict:
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
        cursor.execute(
            "INSERT INTO messages (session_id, student_id, role, content) VALUES (?, ?, ?, ?)",
            (session_id, student_id, role, content)
        )
        conn.commit()

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
                    ORDER BY created_at ASC, message_id ASC
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
    description="Returns the stored chat history for a session."
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
        ORDER BY created_at DESC, message_id DESC
        LIMIT ?
        """,
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()

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
    description="Requests the client model to evaluate a student's academic standing."
)
async def request_student_evaluation(student_id: int, session_id: str, ctx: Context) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

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

    query = """
         SELECT c.title, e.grade, e.status
         FROM enrollments e
         JOIN courses c ON e.course_id = c.course_id
         WHERE e.student_id = ?
     """
    cursor.execute(query, (student_id,))
    courses = cursor.fetchall()
    conn.close()

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

    store_message(session_id=session_id, role="user", content=user_prompt, student_id=student_id)

    response = await ctx.sample(
        messages=user_prompt,
        max_tokens=150
    )

    store_message(session_id=session_id, role="assistant", content=response.text, student_id=student_id)

    return {
        "status": "success",
        "session_id": session_id,
        "evaluation": response.text
    }


# ======================================================
# Server Execution
# ======================================================

# الاستيراد هنا، في آخر الملف، بعد ما get_db_connection وكل الأدوات
# المشتركة معرّفة بالفعل -- بيتفادى circular import كان بيحصل لما
# scholarship_tools.py / internship_tools.py بيحاولوا يعملوا
# "from server import get_db_connection" وهي لسه مانتعرّفتش.

import internship_tools

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