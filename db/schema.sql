
CREATE TABLE IF NOT EXISTS instructors (
    instructor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    instructor_id INTEGER,
    credits INTEGER NOT NULL,
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