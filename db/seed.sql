
INSERT INTO instructors (instructor_id, name, email) VALUES 
(1, 'Dr. Ahmed Hassan', 'ahmed.hassan@brightpeak.edu'),
(2, 'Prof. Sarah Jenkins', 'sarah.j@brightpeak.edu'),
(3, 'Dr. Mahmoud Abdelrahman', 'mahmoud.a@brightpeak.edu'),
(4, 'Dr. Mona Zaki', 'mona.zaki@brightpeak.edu');


INSERT INTO courses (course_id, title, instructor_id, credits) VALUES 
(1, 'Introduction to Computer Science', 1, 3),
(2, 'Advanced Machine Learning', 2, 4),
(3, 'Database Management Systems', 3, 3),
(4, 'Software Engineering Principles', 1, 3),
(5, 'Artificial Intelligence Ethics', 4, 2);


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