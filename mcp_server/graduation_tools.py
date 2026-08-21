"""
mcp_server/graduation_tools.py

أدوات MCP خاصة بـ graph #2 (تصريح التخرج). بتتسجل عن طريق دالة register()
بدل الاستيراد المباشر لـ mcp من server.py -- ده بيتفادى مشكلة الاستيراد
الدائري (circular import) اللي بتحصل لو الملف اتفتح كـ subprocess منفصل.

في server.py محتاجة سطرين بعد تعريف mcp:
    import graduation_tools
    graduation_tools.register(mcp, get_db_connection)
"""


def register(mcp, get_db_connection):

    @mcp.tool(
        name="submit_graduation_application",
        description="يسجل طلب تصريح تخرج جديد لطالب في قسم معي",
    )
    def submit_graduation_application(student_id: int, department: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
            if not cursor.fetchone():
                return {"status": "error", "message": f"الطالب {student_id} غير موجود."}

            cursor.execute(
                "INSERT INTO graduation_applications (student_id, department, state) VALUES (?, ?, 'application_submitted')",
                (student_id, department),
            )
            conn.commit()
            return {"status": "success", "application_id": cursor.lastrowid}
        except Exception as e:
            return {"status": "error", "message": f"Database exception: {str(e)}"}
        finally:
            conn.close()

    @mcp.tool(
        name="get_academic_status",
        description="Constrained ReAct: يحسب عدد الساعات المكتملة ومعدل الطالب، ويقارنهم بمتطلبات التخرج الرسمية للقسم.",
    )
    def get_academic_status(student_id: int, department: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT SUM(c.credits) as completed_credits, AVG(e.grade) as avg_grade
            FROM enrollments e JOIN courses c ON c.course_id = e.course_id
            WHERE e.student_id = ? AND e.status = 'COMPLETED'
            """,
            (student_id,),
        )
        row = cursor.fetchone()
        completed_credits = row["completed_credits"] or 0
        avg_grade = row["avg_grade"] or 0
        gpa_equivalent = avg_grade / 25

        cursor.execute("SELECT required_credits, minimum_gpa FROM graduation_requirements WHERE department = ?", (department,))
        req = cursor.fetchone()
        conn.close()

        if not req:
            return {"status": "error", "message": f"مفيش متطلبات مسجلة لقسم '{department}'."}

        clear = completed_credits >= req["required_credits"] and gpa_equivalent >= req["minimum_gpa"]

        return {
            "status": "success",
            "clear": clear,
            "completed_credits": completed_credits,
            "required_credits": req["required_credits"],
            "gpa_equivalent": round(gpa_equivalent, 2),
            "minimum_gpa": req["minimum_gpa"],
        }

    @mcp.tool(
        name="get_financial_status",
        description="Constrained ReAct: يتحقق من وجود مستحقات مالية معلقة على الطالب.",
    )
    def get_financial_status(student_id: int) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT outstanding_amount FROM student_financials WHERE student_id = ?", (student_id,))
        row = cursor.fetchone()
        conn.close()

        outstanding = row["outstanding_amount"] if row else 0
        return {"status": "success", "clear": outstanding <= 0, "outstanding_amount": outstanding}

    @mcp.tool(
        name="get_library_status",
        description="Constrained ReAct: يتحقق من وجود كتب متأخرة أو غرامات مكتبة معلقة.",
    )
    def get_library_status(student_id: int) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT has_debt, fines FROM student_library_status WHERE student_id = ?", (student_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return {"status": "error", "message": f"مفيش سجل مكتبة للطالب {student_id}."}

        return {"status": "success", "clear": row["has_debt"] == 0, "fines": row["fines"]}

    @mcp.tool(
        name="get_required_documents",
        description="Constrained ReAct: يتحقق من رفع واعتماد كل المستندات المطلوبة للتخرج.",
    )
    def get_required_documents(student_id: int) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT document_type, uploaded, verified FROM student_documents WHERE student_id = ?",
            (student_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        required_types = {"graduation_form"}
        have_types = {r["document_type"] for r in rows if r["uploaded"] and r["verified"]}
        missing = required_types - have_types

        return {"status": "success", "clear": len(missing) == 0, "missing_documents": list(missing)}

    @mcp.tool(
        name="update_graduation_state",
        description="الأداة المصرح بيها الوحيدة لتغيير حالة طلب التخرج (state).",
    )
    def update_graduation_state(application_id: int, new_state: str) -> dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE graduation_applications SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE application_id = ?",
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