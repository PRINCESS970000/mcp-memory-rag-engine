INSERT OR IGNORE INTO enrollments (enrollment_id, student_id, course_id, grade, status)
VALUES (100, 4, 4, 90.0, 'COMPLETED');
 
-- تأكيد إن باقي الفحوصات (مالي/مكتبة/مستندات) واضحة عشان نختبر الأكاديمي بمعزل عن الباقي
INSERT OR IGNORE INTO student_financials (student_id, outstanding_amount) VALUES (4, 0);
INSERT OR IGNORE INTO student_library_status (student_id, has_debt, fines) VALUES (4, 0, 0);
INSERT OR IGNORE INTO student_documents (student_id, document_type, uploaded, verified)
VALUES (4, 'graduation_form', 1, 1);
 