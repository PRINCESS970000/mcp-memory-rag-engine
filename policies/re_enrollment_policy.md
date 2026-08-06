---
policy_type: re_enrollment
document_id: POL-RE-001
last_reviewed_date: 2026-02-01
version: 1.0
---

# BrightPeak Re-Enrollment Policy

## Section 1 — Purpose
This policy governs when a student may withdraw from a course they are
currently enrolled in, and the conditions under which they may re-enroll
in that same course afterward. It applies to any enrollment record in the
system, identified by student_id and course_id.

## Section 2 — Withdrawing From a Course
A student may withdraw from a course at any time while their enrollment
status for that course is ENROLLED. Withdrawing sets the enrollment
status to DROPPED. A student may not withdraw from an enrollment that is
already COMPLETED or already DROPPED.

## Section 3 — Re-Enrollment Eligibility

### Section 3.1 — First or Second Drop
If a student's enrollment in a given course has been set to DROPPED one
or two times in total, the student may re-enroll in that same course
immediately, with no waiting period and no approval required. A new
enrollment record is created with status ENROLLED and grade unset.

### Section 3.2 — Third Drop and Beyond
If a student has been DROPPED from the same course three or more times,
they may not re-enroll in that course on their own. Re-enrollment
requires written approval from the instructor assigned to that course
(the instructor_id on the course record). A student whose account has
role TA, INSTRUCTOR, or ADMIN may grant this approval on another
student's behalf; a student with role STUDENT cannot approve their own
exception.

## Section 4 — Re-Enrollment and Certificates
A DROPPED enrollment never generates a certificate. Only an enrollment
that reaches status COMPLETED with a recorded grade is eligible for
certificate issuance, as described in the Certificate Reissue Policy,
Section 1.
