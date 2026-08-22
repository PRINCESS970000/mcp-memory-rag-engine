def _ensure_tool_status_table(get_db_connection):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mcp_tool_status (
            tool_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
 
 
def _is_enabled(get_db_connection, tool_name: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT enabled FROM mcp_tool_status WHERE tool_name = ?", (tool_name,))
    row = cursor.fetchone()
    conn.close()
    return True if row is None else bool(row["enabled"])
 
 
def register(mcp, get_db_connection):
    _ensure_tool_status_table(get_db_connection)
 
    TOOL_NAMES = [
        "submit_graduation_application",
        "get_academic_status",
        "get_financial_status",
        "get_library_status",
        "get_required_documents",
        "update_graduation_state",
    ]
    conn = get_db_connection()
    cursor = conn.cursor()
    for name in TOOL_NAMES:
        cursor.execute("INSERT OR IGNORE INTO mcp_tool_status (tool_name, enabled) VALUES (?, 1)", (name,))
    conn.commit()
    conn.close()
 
    @mcp.tool(
        name="submit_graduation_application",
        description="يسجل طلب تصريح تخرج جديد لطالب في قسم معين.",
    )
    def submit_graduation_application(student_id: int, department: str) -> dict:
        if not _is_enabled(get_db_connection, "submit_graduation_application"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
        description="Constrained ReAct: يحسب الساعات المكتملة ومعدل الطالب ويقارنهم بمتطلبات التخرج.",
    )
    def get_academic_status(student_id: int, department: str) -> dict:
        if not _is_enabled(get_db_connection, "get_academic_status"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
            "status": "success", "clear": clear,
            "completed_credits": completed_credits, "required_credits": req["required_credits"],
            "gpa_equivalent": round(gpa_equivalent, 2), "minimum_gpa": req["minimum_gpa"],
        }
 
    @mcp.tool(
        name="get_financial_status",
        description="Constrained ReAct: يتحقق من وجود مستحقات مالية معلقة على الطالب.",
    )
    def get_financial_status(student_id: int) -> dict:
        if not _is_enabled(get_db_connection, "get_financial_status"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
        if not _is_enabled(get_db_connection, "get_library_status"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
        if not _is_enabled(get_db_connection, "get_required_documents"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
        if not _is_enabled(get_db_connection, "update_graduation_state"):
            return {"status": "error", "message": "Tool disabled by admin."}
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
 