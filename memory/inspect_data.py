from episodic_store import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=== All episodic_events for student 7 ===")
cursor.execute("SELECT event_id, event_summary, created_at FROM episodic_events WHERE student_id = 7 AND event_type = 're_enrollment_decision' ORDER BY event_id")
for row in cursor.fetchall():
    print(dict(row))

print("\n=== All semantic_facts for student 7 ===")
cursor.execute("SELECT fact_id, fact_text, version, is_current, superseded_by FROM semantic_facts WHERE student_id = 7 ORDER BY fact_id")
for row in cursor.fetchall():
    print(dict(row))

conn.close()