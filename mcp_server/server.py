import sqlite3
import os
import re
from fastmcp import FastMCP, Context



mcp = FastMCP("Brightpeak Academy Server")


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "brightpeak.db")

def get_db_connection():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

import time

@mcp.tool(
    name="generate_academic_report",
    description="Generates a comprehensive academic report for all courses and students."
)
async def generate_academic_report(ctx: Context) -> dict:

    import asyncio

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
    name="request_student_evaluation",
    description="Requests the client model to evaluate a student's academic standing based on their grades using sampling."
)
async def request_student_evaluation(student_id: int, ctx: Context) -> dict:
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

    # Build prompt
    course_details = ""

    for course in courses:
        course_details += (
            f"- {course['title']}\n"
            f"  Grade : {course['grade']}\n"
            f"  Status: {course['status']}\n\n"
        )

    prompt = f"""
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
    # Ask the client model
    response = await ctx.sample(
        messages=prompt,
        max_tokens=150
    )

    return {
        "status": "success",
        "evaluation": response.text
    }
import sys

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