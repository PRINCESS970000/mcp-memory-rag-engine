-- ============================================================
-- إضافة على نفس brightpeak.db، خاص بـ state graph: Graduation Clearance
-- ============================================================

CREATE TABLE IF NOT EXISTS graduation_requirements (
    department TEXT PRIMARY KEY,
    required_credits INTEGER NOT NULL,
    minimum_gpa REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS student_financials (
    student_id INTEGER PRIMARY KEY,
    outstanding_amount REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS student_library_status (
    student_id INTEGER PRIMARY KEY,
    has_debt INTEGER NOT NULL DEFAULT 0,     
    fines REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS student_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    document_type TEXT NOT NULL,             
    uploaded INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS graduation_applications (
    application_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    department TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'application_submitted',

    total_corrections INTEGER NOT NULL DEFAULT 0,
    max_corrections INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);


INSERT OR IGNORE INTO graduation_requirements (department, required_credits, minimum_gpa)
VALUES ('cs_fundamentals', 12, 2.0);

INSERT OR IGNORE INTO student_financials (student_id, outstanding_amount) VALUES (1, 0);
INSERT OR IGNORE INTO student_library_status (student_id, has_debt, fines) VALUES (1, 0, 0);
INSERT OR IGNORE INTO student_documents (student_id, document_type, uploaded, verified)
VALUES (1, 'graduation_form', 1, 1);