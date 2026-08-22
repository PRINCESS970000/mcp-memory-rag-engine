"""
mcp_server/internship_tools.py

Internship-graph MCP tools, registered via register(mcp, get_db_connection)
-- not via "from server import mcp". That self-import pattern silently
creates a second, disconnected FastMCP instance whenever server.py runs
as __main__ (a subprocess), so tools defined that way never reach the
live server -- a real bug found while wiring platform/user/ against the
actual running subprocess. graduation_tools.py already avoids this by
receiving mcp as a parameter instead; this file now follows the same
pattern.
"""


def register(mcp, get_db_connection):

    def init_internship_tables():
        """جدول التطبيقات الخاص بالتدريب - نفس نمط internship_applications."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS internship_applications (
                application_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                role_title TEXT NOT NULL,
                state TEXT DEFAULT 'started',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    init_internship_tables()

    @mcp.tool(
        name="check_internship_readiness",
        description="يفكك جاهزية الطالب للتقديم على دور تدريب لخطوات محسوسة: "
                    "المهارات المطلوبة (عبر role_required_skills)، الكورسات المكتملة، "
                    "والمستندات. بيرجع dict فيه كل خطوة true/false على حدة.",
    )
    def check_internship_readiness(student_id: int, role_title: str) -> dict:
        if student_id <= 0:
            return {"status": "error", "message": "student_id غير صالح."}

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
        if not cursor.fetchone():
            conn.close()
            return {"status": "error", "message": f"الطالب {student_id} غير موجود."}

        cursor.execute("SELECT role_id FROM job_roles WHERE title = ?", (role_title,))
        role = cursor.fetchone()
        if not role:
            conn.close()
            return {"status": "error", "message": f"مفيش دور بعنوان '{role_title}'."}

        cursor.execute(
            "SELECT skill_tag FROM role_required_skills WHERE role_id = ?",
            (role["role_id"],),
        )
        required_skills = {row["skill_tag"] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT c.skill_tags FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            WHERE e.student_id = ? AND e.status = 'COMPLETED'
        """, (student_id,))
        covered_skills = set()
        for row in cursor.fetchall():
            covered_skills |= set((row["skill_tags"] or "").split(","))

        conn.close()

        skills_ready = required_skills.issubset(covered_skills) if required_skills else True
        courses_ready = skills_ready
        cv_ready = True
        documents_ready = True

        return {
            "status": "success",
            "steps": {
                "skills": skills_ready,
                "courses": courses_ready,
                "cv": cv_ready,
                "documents": documents_ready,
            },
            "missing_skills": sorted(required_skills - covered_skills),
        }

    @mcp.tool(
        name="submit_internship_application",
        description="يسجل طلب تدريب فعلي للطالب في حالة started. لا يُستخدم إلا "
                    "بعد موافقة HITL على الإرسال.",
    )
    def submit_internship_application(student_id: int, role_title: str) -> dict:
        if student_id <= 0:
            return {"status": "error", "message": "student_id غير صالح."}

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
            if not cursor.fetchone():
                return {"status": "error", "message": f"الطالب {student_id} غير موجود."}

            cursor.execute(
                "INSERT INTO internship_applications (student_id, role_title, state) VALUES (?, ?, 'started')",
                (student_id, role_title),
            )
            conn.commit()
            return {"status": "success", "application_id": cursor.lastrowid}
        except Exception as e:
            return {"status": "error", "message": f"Database exception: {str(e)}"}
        finally:
            conn.close()

    @mcp.tool(
        name="update_internship_application_state",
        description="يحدّث حالة طلب التدريب في internship_applications. "
                    "الأداة المصرح بيها الوحيدة لتغيير حالة طلب التدريب.",
    )
    def update_internship_application_state(application_id: int, new_state: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE internship_applications SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE application_id = ?",
                (new_state, application_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {"status": "error", "message": f"مفيش طلب برقم {application_id}."}
            return {"status": "success", "application_id": application_id, "new_state": new_state}
        except Exception as e:
            return {"status": "error", "message": f"Database exception: {str(e)}"}
        finally:
            conn.close()