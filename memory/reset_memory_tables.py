"""
Wipes only the tables we created for memory (episodic_events,
semantic_facts). Does NOT touch students/courses/enrollments/messages.
Safe to re-run any time you want a clean slate for testing.
"""

from episodic_store import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("DELETE FROM episodic_events")
cursor.execute("DELETE FROM semantic_facts")

# Reset the autoincrement counters too, so IDs start from 1 again
cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('episodic_events', 'semantic_facts')")

conn.commit()
conn.close()

print("episodic_events and semantic_facts cleared.")