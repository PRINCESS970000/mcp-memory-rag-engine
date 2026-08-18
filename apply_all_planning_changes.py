"""
apply_all_planning_changes.py

Brings db/brightpeak.db fully up to date for the Learning Path Planning
agent, no matter what's already in it (fresh db, db with only the original
5 courses, or db that already has Memory/RAG's episodic_events/
semantic_facts tables). Every step checks before it acts, so this is safe
to run more than once.

Usage (from the project root):
    python apply_all_planning_changes.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "brightpeak.db")


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def row_exists(cursor, table, where_clause, params):
    cursor.execute(f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1", params)
    return cursor.fetchone() is not None


NEW_COLUMNS_BY_TABLE = {
    "courses": {
        "price": "REAL DEFAULT 0",
        "weekly_hours": "REAL DEFAULT 0",
        "duration_weeks": "INTEGER DEFAULT 0",
        "start_date": "TEXT",
        "end_date": "TEXT",
        "difficulty": "TEXT",
        "skill_tags": "TEXT",
    },
    "instructors": {
        "rating": "REAL DEFAULT 4.0",
    },
}

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

# instructor_id -> rating
INSTRUCTOR_RATINGS = {1: 4.6, 2: 4.8, 3: 4.1, 4: 4.3}

# course_id -> (price, weekly_hours, duration_weeks, start_date, end_date, difficulty, skill_tags)
EXISTING_COURSE_PLANNING_DATA = {
    1: (150, 6, 6, "2026-09-01", "2026-10-13", "beginner", "programming,cs_fundamentals"),
    2: (400, 10, 8, "2026-10-13", "2026-12-08", "advanced", "machine_learning,statistics,python"),
    3: (250, 8, 6, "2026-09-01", "2026-10-13", "intermediate", "databases,sql"),
    4: (200, 6, 5, "2026-09-08", "2026-10-13", "intermediate", "software_engineering"),
    5: (80, 3, 3, "2026-09-01", "2026-09-22", "beginner", "ai_ethics"),
}

# New courses (6-14): (id, title, instructor_id, credits, price, weekly_hours,
# duration_weeks, start_date, end_date, difficulty, skill_tags)
NEW_COURSES = [
    (6, "Python Programming Basics", 2, 3, 100, 5, 4, "2026-09-01", "2026-09-29", "beginner", "python,programming"),
    (7, "Statistics for Data Science", 4, 3, 180, 6, 5, "2026-09-01", "2026-10-06", "intermediate", "statistics"),
    (8, "Data Visualization with Python", 2, 3, 150, 5, 4, "2026-10-13", "2026-11-10", "intermediate", "data_visualization,python"),
    (9, "Cloud Computing Fundamentals", 3, 3, 300, 8, 8, "2026-10-13", "2026-12-08", "intermediate", "cloud_computing"),
    (10, "Data Engineering Pipelines", 2, 4, 350, 9, 7, "2026-10-20", "2026-12-08", "advanced", "data_engineering,sql,python"),
    (11, "Deep Learning Foundations", 2, 4, 450, 10, 8, "2026-12-15", "2027-02-09", "advanced", "deep_learning,machine_learning"),
    (12, "Business Communication for Tech Teams", 4, 1, 60, 2, 3, "2026-09-01", "2026-09-22", "beginner", "communication"),
    (13, "Product Management Essentials", 1, 3, 220, 5, 5, "2026-09-08", "2026-10-13", "intermediate", "product_management"),
    (14, "SQL for Data Analysis", 3, 2, 130, 4, 4, "2026-09-01", "2026-09-29", "beginner", "sql,data_analysis"),
]

PREREQUISITES = [(2, 6), (2, 7), (3, 1), (4, 1), (8, 6), (9, 1), (10, 3), (10, 6), (11, 2), (14, 1)]

JOB_ROLES = [(1, "Data Scientist"), (2, "Software Engineer"), (3, "ML Engineer"), (4, "Data Analyst")]

ROLE_SKILLS = [
    (1, "programming"), (1, "statistics"), (1, "machine_learning"), (1, "sql"), (1, "data_visualization"),
    (2, "programming"), (2, "software_engineering"), (2, "cs_fundamentals"), (2, "databases"),
    (3, "programming"), (3, "machine_learning"), (3, "deep_learning"), (3, "cloud_computing"), (3, "statistics"),
    (4, "sql"), (4, "data_visualization"), (4, "statistics"), (4, "communication"),
]

# (student_id, target_role_id, weekly_hours_available, budget, target_date)
LEARNING_GOALS = [
    (4, 4, 12, 600, "2026-11-01"),   # Youssef -> Data Analyst
    (6, 3, 10, 500, "2027-03-01"),   # Hoda -> ML Engineer
    (1, 1, 10, 700, "2027-02-01"),   # Omar -> Data Scientist
    (8, 2, 6, 350, "2026-10-15"),    # Salma -> Software Engineer
    (7, 2, 8, 400, "2026-11-01"),    # Kareem -> Software Engineer
]


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1) missing columns
    for table, columns in NEW_COLUMNS_BY_TABLE.items():
        for column, decl in columns.items():
            if not column_exists(cursor, table, column):
                print(f"Adding {table}.{column} ...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            else:
                print(f"{table}.{column} already exists, skipping.")

    # 2) missing tables
    for name, ddl in NEW_TABLES.items():
        if not table_exists(cursor, name):
            print(f"Creating table {name} ...")
            cursor.execute(ddl)
        else:
            print(f"Table {name} already exists, skipping.")

    conn.commit()

    # 3) instructor ratings
    for instructor_id, rating in INSTRUCTOR_RATINGS.items():
        cursor.execute("UPDATE instructors SET rating = ? WHERE instructor_id = ?", (rating, instructor_id))

    # 4) fill in planning columns on the 5 pre-existing courses (safe UPDATE, no conflict)
    for course_id, values in EXISTING_COURSE_PLANNING_DATA.items():
        if row_exists(cursor, "courses", "course_id = ?", (course_id,)):
            cursor.execute(
                """UPDATE courses SET price=?, weekly_hours=?, duration_weeks=?,
                   start_date=?, end_date=?, difficulty=?, skill_tags=?
                   WHERE course_id=?""",
                (*values, course_id),
            )
        else:
            print(f"WARNING: course_id {course_id} not found -- skipping (unexpected).")

    # 5) new courses (6-14) -- only insert if not already present
    for course in NEW_COURSES:
        course_id = course[0]
        if not row_exists(cursor, "courses", "course_id = ?", (course_id,)):
            cursor.execute(
                """INSERT INTO courses
                   (course_id, title, instructor_id, credits, price, weekly_hours,
                    duration_weeks, start_date, end_date, difficulty, skill_tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                course,
            )
        else:
            print(f"Course {course_id} already exists, skipping.")

    # 6) prerequisites, job roles, role skills, learning goals -- only insert if missing
    for course_id, prereq_id in PREREQUISITES:
        if not row_exists(cursor, "course_prerequisites",
                           "course_id = ? AND prerequisite_course_id = ?", (course_id, prereq_id)):
            cursor.execute(
                "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (?, ?)",
                (course_id, prereq_id),
            )

    for role_id, title in JOB_ROLES:
        if not row_exists(cursor, "job_roles", "role_id = ?", (role_id,)):
            cursor.execute("INSERT INTO job_roles (role_id, title) VALUES (?, ?)", (role_id, title))

    for role_id, skill_tag in ROLE_SKILLS:
        if not row_exists(cursor, "role_required_skills",
                           "role_id = ? AND skill_tag = ?", (role_id, skill_tag)):
            cursor.execute(
                "INSERT INTO role_required_skills (role_id, skill_tag) VALUES (?, ?)",
                (role_id, skill_tag),
            )

    for student_id, role_id, hours, budget, target_date in LEARNING_GOALS:
        if not row_exists(cursor, "learning_goals",
                           "student_id = ? AND target_role_id = ?", (student_id, role_id)):
            cursor.execute(
                """INSERT INTO learning_goals
                   (student_id, target_role_id, weekly_hours_available, budget, target_date)
                   VALUES (?,?,?,?,?)""",
                (student_id, role_id, hours, budget, target_date),
            )

    conn.commit()
    conn.close()
    print("\nAll planning schema + seed data applied. Safe to re-run any time.")


if __name__ == "__main__":
    main()
