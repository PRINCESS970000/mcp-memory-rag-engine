
INSERT INTO instructors (instructor_id, name, email) VALUES 
(1, 'Dr. Ahmed Hassan', 'ahmed.hassan@brightpeak.edu'),
(2, 'Prof. Sarah Jenkins', 'sarah.j@brightpeak.edu'),
(3, 'Dr. Mahmoud Abdelrahman', 'mahmoud.a@brightpeak.edu'),
(4, 'Dr. Mona Zaki', 'mona.zaki@brightpeak.edu');


INSERT INTO students (student_id, name, email, role) VALUES 
(1, 'Omar Khaled', 'omar.k@brightpeak.edu', 'STUDENT'),
(2, 'Mariam Ali', 'mariam.a@brightpeak.edu', 'INSTRUCTOR'),
(3, 'Prinsisa Mohamed', 'prinsisa.m@brightpeak.edu', 'ADMIN'),
(4, 'Youssef Ibrahim', 'youssef.i@brightpeak.edu', 'STUDENT'),
(5, 'Nour El-Din', 'nour.e@brightpeak.edu', 'TA'),
(6, 'Hoda Mansour', 'hoda.m@brightpeak.edu', 'STUDENT'),
(7, 'Kareem Reda', 'kareem.r@brightpeak.edu', 'STUDENT'),
(8, 'Salma Farouk', 'salma.f@brightpeak.edu', 'STUDENT');


INSERT INTO enrollments (enrollment_id, student_id, course_id, grade, status) VALUES 
(1, 1, 1, 95.5, 'COMPLETED'),
(2, 1, 2, 88.0, 'ENROLLED'),
(3, 1, 3, 91.2, 'COMPLETED'),
(4, 4, 1, 74.0, 'COMPLETED'),
(5, 4, 3, 82.5, 'ENROLLED'),
(6, 6, 2, 98.0, 'COMPLETED'),
(7, 7, 1, 45.0, 'DROPPED'),
(8, 8, 5, NULL, 'ENROLLED');


INSERT INTO certificates (certificate_id, enrollment_id, certificate_code) VALUES 
(1, 1, 'CERT-CS101-2026-001'),
(2, 3, 'CERT-DBMS-2026-002'),
(3, 4, 'CERT-CS101-2026-003'),
(4, 6, 'CERT-AML-2026-004');

INSERT INTO courses (course_id, title, instructor_id, credits, price, weekly_hours, duration_weeks, start_date, end_date, difficulty, skill_tags) VALUES
(1,  'Introduction to Computer Science', 1, 3, 150, 6,  6, '2026-09-01', '2026-10-13', 'beginner',     'programming,cs_fundamentals'),
(2,  'Advanced Machine Learning',        2, 4, 400, 10, 8, '2026-10-13', '2026-12-08', 'advanced',     'machine_learning,statistics,python'),
(3,  'Database Management Systems',      3, 3, 250, 8,  6, '2026-09-01', '2026-10-13', 'intermediate', 'databases,sql'),
(4,  'Software Engineering Principles',  1, 3, 200, 6,  5, '2026-09-08', '2026-10-13', 'intermediate', 'software_engineering'),
(5,  'Artificial Intelligence Ethics',   4, 2, 80,  3,  3, '2026-09-01', '2026-09-22', 'beginner',     'ai_ethics'),
(6,  'Python Programming Basics',        2, 3, 100, 5,  4, '2026-09-01', '2026-09-29', 'beginner',     'python,programming'),
(7,  'Statistics for Data Science',      4, 3, 180, 6,  5, '2026-09-01', '2026-10-06', 'intermediate', 'statistics'),
(8,  'Data Visualization with Python',   2, 3, 150, 5,  4, '2026-10-13', '2026-11-10', 'intermediate', 'data_visualization,python'),
(9,  'Cloud Computing Fundamentals',     3, 3, 300, 8,  8, '2026-10-13', '2026-12-08', 'intermediate', 'cloud_computing'),
(10, 'Data Engineering Pipelines',       2, 4, 350, 9,  7, '2026-10-20', '2026-12-08', 'advanced',     'data_engineering,sql,python'),
(11, 'Deep Learning Foundations',        2, 4, 450, 10, 8, '2026-12-15', '2027-02-09', 'advanced',     'deep_learning,machine_learning'),
(12, 'Business Communication for Tech Teams', 4, 1, 60, 2, 3, '2026-09-01', '2026-09-22', 'beginner',  'communication'),
(13, 'Product Management Essentials',   1, 3, 220, 5,  5, '2026-09-08', '2026-10-13', 'intermediate', 'product_management'),
(14, 'SQL for Data Analysis',           3, 2, 130, 4,  4, '2026-09-01', '2026-09-29', 'beginner',     'sql,data_analysis');


INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES
(2, 6),   
(2, 7),   
(3, 1),   
(4, 1),   
(8, 6),   
(9, 1),   
(10, 3),  
(10, 6), 
(11, 2),  
(14, 1);  

INSERT INTO job_roles (role_id, title) VALUES
(1, 'Data Scientist'),
(2, 'Software Engineer'),
(3, 'ML Engineer'),
(4, 'Data Analyst');

INSERT INTO role_required_skills (role_id, skill_tag) VALUES
(1, 'programming'), (1, 'statistics'), (1, 'machine_learning'), (1, 'sql'), (1, 'data_visualization'),
(2, 'programming'), (2, 'software_engineering'), (2, 'cs_fundamentals'), (2, 'databases'),
(3, 'programming'), (3, 'machine_learning'), (3, 'deep_learning'), (3, 'cloud_computing'), (3, 'statistics'),
(4, 'sql'), (4, 'data_visualization'), (4, 'statistics'), (4, 'communication');


INSERT INTO learning_goals (student_id, target_role_id, weekly_hours_available, budget, target_date) VALUES
(4, 4, 12, 600, '2026-11-01'),
(1, 1, 10, 700, '2027-02-01'),
(6, 3, 15, 1000, '2027-03-01'),
(8, 2, 8, 500, '2026-12-01'),
(7, 2, 8, 400, '2026-11-01');