"""
Idempotent migration: brings an existing db/brightpeak.db up to date with the
team's current schema.sql (Learning Path Planning agent additions) without
touching or losing any existing rows.

Safe to run more than once — every step checks first before altering anything.

Usage:
    python apply_schema_migration.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "brightpeak.db")


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


# Matches the `courses` block in schema.sql
NEW_COURSE_COLUMNS = {
    "price": "REAL DEFAULT 0",
    "weekly_hours": "REAL DEFAULT 0",
    "duration_weeks": "INTEGER DEFAULT 0",
    "start_date": "TEXT",
    "end_date": "TEXT",
    "difficulty": "TEXT",
    "skill_tags": "TEXT",
}

# Matches the new standalone CREATE TABLE blocks in schema.sql, verbatim
NEW_TABLES = {
    "course_prerequisites": """
        CREATE TABLE course_prerequisites (
            course_id INTEGER,
            prerequisite_course_id INTEGER,
            FOREIGN KEY (course_id) REFERENCES courses(course_id),
            FOREIGN KEY (prerequisite_course_id) REFERENCES courses(course_id)
        )
    """,
    "job_roles": """
        CREATE TABLE job_roles (
            role_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL
        )
    """,
    "role_required_skills": """
        CREATE TABLE role_required_skills (
            role_id INTEGER,
            skill_tag TEXT,
            FOREIGN KEY (role_id) REFERENCES job_roles(role_id)
        )
    """,
    "learning_goals": """
        CREATE TABLE learning_goals (
            goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            target_role_id INTEGER,
            weekly_hours_available REAL,
            budget REAL,
            target_date TEXT,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (target_role_id) REFERENCES job_roles(role_id)
        )
    """,
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for column, decl in NEW_COURSE_COLUMNS.items():
        if not column_exists(cursor, "courses", column):
            print(f"Adding courses.{column} ...")
            cursor.execute(f"ALTER TABLE courses ADD COLUMN {column} {decl}")
        else:
            print(f"courses.{column} already exists, skipping.")

    for name, ddl in NEW_TABLES.items():
        if not table_exists(cursor, name):
            print(f"Creating table {name} ...")
            cursor.execute(ddl)
        else:
            print(f"Table {name} already exists, skipping.")

    conn.commit()
    conn.close()
    print("Schema migration complete. No existing rows were touched.")


if __name__ == "__main__":
    main()
