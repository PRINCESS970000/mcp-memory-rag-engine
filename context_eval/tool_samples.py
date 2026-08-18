"""
Builds a small in-memory SQLite DB matching the Brightpeak schema and runs
standalone versions of the 6 original MCP tools against it, so we have real
(not hand-typed) JSON outputs to seed the synthetic transcript with.

Tools covered (the original 6, before the messages/rolling-buffer additions):
  1. get_student_profile
  2. list_all_courses
  3. enroll_student
  4. update_student_grade
  5. generate_academic_report
  6. request_student_evaluation  (sampling call replaced with a fixed string,
     since there's no live model/client here)
"""

import sqlite3
import re
import json


def build_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE students (
        student_id INTEGER PRIMARY KEY,
        name TEXT, email TEXT, role TEXT
    );
    CREATE TABLE instructors (
        instructor_id INTEGER PRIMARY KEY,
        name TEXT
    );
    CREATE TABLE courses (
        course_id INTEGER PRIMARY KEY,
        title TEXT, credits INTEGER, instructor_id INTEGER
    );
    CREATE TABLE enrollments (
        enrollment_id INTEGER PRIMARY KEY,
        student_id INTEGER, course_id INTEGER,
        grade REAL, status TEXT
    );
    """)

    # A realistically sized roster -- enough that each tool call returns a
    # meaningfully large JSON payload, matching the lab's cost note (lean on
    # large, realistic INPUT transcripts rather than trying to inflate
    # output).
    first_names = ["Youssef", "Omar", "Nour", "Mariam", "Karim", "Laila",
                    "Ahmed", "Sara", "Hana", "Youssef", "Fady", "Dina",
                    "Aya", "Ziad", "Rana"]
    last_names = ["Ibrahim", "Khaled", "Adel", "Sami", "Fathy", "Hassan",
                  "Nabil", "Farid", "Amer", "Sobhy", "Kamal", "Rashed",
                  "Tawfik", "Gaber", "Aziz"]

    students = []
    for i in range(1, 16):
        fn, ln = first_names[i - 1], last_names[i - 1]
        email = f"{fn.lower()}.{ln[0].lower()}{i}@brightpeak.edu"
        students.append((i, f"{fn} {ln}", email, "STUDENT"))
    cur.executemany("INSERT INTO students VALUES (?,?,?,?)", students)

    cur.executemany(
        "INSERT INTO instructors VALUES (?,?)",
        [(1, "Dr. Sara Hassan"), (2, "Dr. Ahmed Fathy"),
         (3, "Dr. Mona Sherif"), (4, "Dr. Khaled Reda")],
    )
    courses = [
        (1, "Data Structures", 3, 1),
        (2, "Operating Systems", 4, 2),
        (3, "Database Systems", 3, 1),
        (4, "Computer Networks", 3, 2),
        (5, "Software Engineering", 4, 3),
        (6, "Machine Learning", 3, 4),
        (7, "Discrete Mathematics", 3, 1),
        (8, "Web Development", 3, 3),
        (9, "Computer Architecture", 4, 2),
        (10, "Algorithms", 3, 4),
    ]
    cur.executemany("INSERT INTO courses VALUES (?,?,?,?)", courses)

    enrollments = []
    eid = 1
    rng_grades = [91.0, 88.5, 76.0, 95.5, 82.0, 67.5, 90.0, None]
    for sid in range(1, 16):
        for cid in range(1, 11):
            if (sid + cid) % 3 == 0:  # sparse but not tiny enrollment matrix
                grade = rng_grades[(sid + cid) % len(rng_grades)]
                status = "COMPLETED" if grade is not None else "ENROLLED"
                enrollments.append((eid, sid, cid, grade, status))
                eid += 1
    cur.executemany("INSERT INTO enrollments VALUES (?,?,?,?,?)", enrollments)
    conn.commit()
    return conn


def get_student_profile(conn, email):
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        return {"status": "error", "message": "Invalid email format."}
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE email = ?", (email,))
    student = cur.fetchone()
    if not student:
        return {"status": "error", "message": f"Student with email '{email}' not found."}
    cur.execute("""
        SELECT c.title, e.grade, e.status
        FROM enrollments e JOIN courses c ON e.course_id = c.course_id
        WHERE e.student_id = ?
    """, (student["student_id"],))
    courses = cur.fetchall()
    return {
        "status": "success",
        "data": {
            "student_id": student["student_id"],
            "name": student["name"],
            "email": student["email"],
            "role": student["role"],
            "enrolled_courses": [dict(r) for r in courses],
        },
    }


def list_all_courses(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT c.course_id, c.title, c.credits, i.name as instructor_name
        FROM courses c LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
    """)
    rows = cur.fetchall()
    return {"status": "success", "courses": [dict(r) for r in rows]}


def enroll_student(conn, student_id, course_id):
    cur = conn.cursor()
    cur.execute("SELECT enrollment_id FROM enrollments WHERE student_id=? AND course_id=?",
                (student_id, course_id))
    if cur.fetchone():
        return {"status": "error", "message": "Student is already enrolled in this course."}
    cur.execute("INSERT INTO enrollments (student_id, course_id, status) VALUES (?,?,'ENROLLED')",
                (student_id, course_id))
    conn.commit()
    return {"status": "success", "message": f"Successfully enrolled student {student_id} in course {course_id}."}


def update_student_grade(conn, student_id, course_id, new_grade, requester_role):
    if requester_role not in ("INSTRUCTOR", "ADMIN"):
        return {"status": "error", "message": f"Authorization denied. Role '{requester_role}' is not permitted to modify grades."}
    cur = conn.cursor()
    cur.execute("UPDATE enrollments SET grade=?, status='COMPLETED' WHERE student_id=? AND course_id=?",
                (new_grade, student_id, course_id))
    conn.commit()
    return {"status": "success", "message": f"Successfully updated grade for student {student_id} in course {course_id} to {new_grade}."}


def generate_academic_report(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM students")
    student_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM courses")
    course_count = cur.fetchone()["c"]
    return {
        "status": "success",
        "message": "Academic report generated successfully with progress tracking.",
        "report_summary": {
            "total_students": student_count,
            "total_courses": course_count,
            "status": "Completed all evaluation steps",
        },
    }


def request_student_evaluation(conn, student_id):
    cur = conn.cursor()
    cur.execute("SELECT name FROM students WHERE student_id=?", (student_id,))
    row = cur.fetchone()
    name = row["name"] if row else "Unknown"
    # No live sampling client here -> a representative fixed evaluation text.
    evaluation = (
        f"Overall Performance: Strong.\n"
        f"{name} shows consistent grades above 85 in completed courses, "
        f"with one course still in progress.\n"
        f"Recommendation: continue current study pattern."
    )
    return {"status": "success", "evaluation": evaluation}


def collect_samples():
    conn = build_db()
    samples = {
        "get_student_profile": get_student_profile(conn, "youssef.i1@brightpeak.edu"),
        "list_all_courses": list_all_courses(conn),
        "enroll_student": enroll_student(conn, 5, 6),
        "update_student_grade": update_student_grade(conn, 1, 3, 95.0, "INSTRUCTOR"),
        "generate_academic_report": generate_academic_report(conn),
        "request_student_evaluation": request_student_evaluation(conn, 1),
    }
    return samples


if __name__ == "__main__":
    samples = collect_samples()
    print(json.dumps(samples, indent=2, ensure_ascii=False))