---
policy_type: grading_permissions
document_id: POL-GP-005
last_reviewed_date: 2026-02-01
version: 1.0
---

# BrightPeak Grading Permissions Policy

## Section 1 — Purpose
This policy defines which account roles may record, change, or approve
enrollment and grade information. Every account has exactly one role:
STUDENT, TA, INSTRUCTOR, or ADMIN.

## Section 2 — Who May Update a Grade
Only the instructor assigned to a course (matching instructor_id on the
course record) or an account with role ADMIN may update a student's
grade. An account with role TA may not update a grade, even for a course
they are enrolled in as a student, and may not update their own grade
under any circumstance.

## Section 3 — Who May Approve Exceptions
Approval for a re-enrollment exception (see the Re-Enrollment Policy,
Section 3.2) or an enrollment dispute correction (see the Enrollment
Dispute Policy, Section 3) requires an account with role INSTRUCTOR for
that specific course, or role ADMIN. Role TA does not carry approval
authority on its own.

## Section 4 — Conflict of Interest
An account may never approve, resolve, or reissue a request tied to its
own student_id, regardless of its role. If a TA, INSTRUCTOR, or ADMIN
account is also the student named in a dispute, grade appeal, or
re-enrollment request, a different qualifying account must handle it.
