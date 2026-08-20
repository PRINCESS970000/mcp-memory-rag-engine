from server import mcp, get_db_connection
 
 
@mcp.tool(
    name="check_scholarship_eligibility",
    description="يتحقق من أهلية الطالب للتقديم على منحة، بناءً على "
                "learning_goals والميزانية المطلوبة المسجلة له.",
)
def check_scholarship_eligibility(student_id: int, requested_amount: float) -> dict:
    if student_id <= 0:
        return {"status": "error", "message": "student_id غير صالح."}
    if requested_amount <= 0:
        return {"status": "error", "message": "requested_amount لازم يكون أكبر من صفر."}
 
    conn = get_db_connection()
    cursor = conn.cursor()
 
    cursor.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = cursor.fetchone()
    if not student:
        conn.close()
        return {"status": "error", "message": f"الطالب {student_id} غير موجود."}
 
    cursor.execute(
        "SELECT * FROM learning_goals WHERE student_id = ? ORDER BY goal_id DESC LIMIT 1",
        (student_id,),
    )
    goal = cursor.fetchone()
    conn.close()
 
    if not goal:
        return {
            "status": "success",
            "eligible": False,
            "reason": "الطالب لسه ماحددش learning goal، مطلوب قبل التقديم على منحة.",
        }
 
    eligible = requested_amount <= (goal["budget"] * 2)
 
    return {
        "status": "success",
        "eligible": eligible,
        "goal_id": goal["goal_id"],
        "registered_budget": goal["budget"],
    }
 
 
@mcp.tool(
    name="submit_scholarship_application",
    description="يسجل طلب منحة جديد للطالب في حالة application_submitted.",
)
def submit_scholarship_application(
    student_id: int, requested_amount: float, sponsor_name: str = None, goal_id: int = None
) -> dict:
    if student_id <= 0 or requested_amount <= 0:
        return {"status": "error", "message": "بيانات غير صالحة."}
 
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO scholarship_applications
                (student_id, goal_id, requested_amount, sponsor_name, state)
            VALUES (?, ?, ?, ?, 'application_submitted')
            """,
            (student_id, goal_id, requested_amount, sponsor_name),
        )
        conn.commit()
        return {"status": "success", "application_id": cursor.lastrowid}
    except Exception as e:
        return {"status": "error", "message": f"Database exception: {str(e)}"}
    finally:
        conn.close()
 
 
@mcp.tool(
    name="update_application_state",
    description="يحدّث حالة طلب المنحة (state) في scholarship_applications. "
                "الأداة المصرح بيها الوحيدة لتغيير حالة الطلب.",
)
def update_application_state(application_id: int, new_state: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE scholarship_applications SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE application_id = ?",
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
 
 
@mcp.tool(
    name="disburse_installment",
    description="ينفذ صرف قسط فعلي من منحة معتمدة، ويسجله في disbursement_installments. "
                "بيرجع status='error' لو حصل عطل فني في التحويل (عشان الـ graph يفتح ticket).",
)
def disburse_installment(application_id: int, installment_number: int, amount: float) -> dict:
    if amount <= 0:
        return {"status": "error", "message": "المبلغ لازم يكون أكبر من صفر."}
 
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT application_id FROM scholarship_applications WHERE application_id = ?",
            (application_id,),
        )
        if not cursor.fetchone():
            return {"status": "error", "message": f"مفيش طلب برقم {application_id}."}
 
        cursor.execute(
            """
            INSERT INTO disbursement_installments
                (application_id, installment_number, amount, status, disbursed_at)
            VALUES (?, ?, ?, 'disbursed', CURRENT_TIMESTAMP)
            """,
            (application_id, installment_number, amount),
        )
        conn.commit()
        return {
            "status": "success",
            "installment_id": cursor.lastrowid,
            "application_id": application_id,
            "amount": amount,
        }
    except Exception as e:

        return {"status": "error", "message": f"failed transfer: {str(e)}"}
    finally:
        conn.close()
 