
CREATE TABLE IF NOT EXISTS instructors (
    instructor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL ,
    rating REAL DEFAULT 4.0
);

CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    instructor_id INTEGER,
    credits INTEGER NOT NULL,
    price REAL DEFAULT 0,
    weekly_hours REAL DEFAULT 0,
    duration_weeks INTEGER DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    difficulty TEXT,        -- beginner/intermediate/advanced
    skill_tags TEXT,        -- comma-separated
    FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id)
);

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT CHECK(role IN ('STUDENT', 'TA', 'INSTRUCTOR', 'ADMIN')) DEFAULT 'STUDENT'
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    grade REAL CHECK(grade >= 0.0 AND grade <= 100.0),
    status TEXT CHECK(status IN ('ENROLLED', 'COMPLETED', 'DROPPED')) DEFAULT 'ENROLLED',
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    certificate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER UNIQUE NOT NULL,
    issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    certificate_code TEXT UNIQUE NOT NULL,
    FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id)
);


CREATE TABLE episodic_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    session_id TEXT,
    event_type TEXT,       
    event_summary TEXT,      
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE semantic_facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    fact_text TEXT,          
    version INTEGER DEFAULT 1,
    is_current BOOLEAN DEFAULT 1,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP,   
    superseded_by INTEGER     
);

CREATE TABLE course_prerequisites (
    course_id INTEGER,
    prerequisite_course_id INTEGER,
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (prerequisite_course_id) REFERENCES courses(course_id)
);


CREATE TABLE job_roles (
    role_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE role_required_skills (
    role_id INTEGER,
    skill_tag TEXT,
    FOREIGN KEY (role_id) REFERENCES job_roles(role_id)
);

CREATE TABLE learning_goals (
    goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    target_role_id INTEGER,
    weekly_hours_available REAL,
    budget REAL,
    target_date TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (target_role_id) REFERENCES job_roles(role_id)
); 