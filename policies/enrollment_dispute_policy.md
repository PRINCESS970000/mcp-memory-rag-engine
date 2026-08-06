---
policy_type: enrollment_dispute
document_id: POL-ED-004
last_reviewed_date: 2026-02-01
version: 1.0
---

# BrightPeak Enrollment Dispute Policy

## Section 1 — Purpose
This policy covers complaints about an enrollment record that is
incorrect for reasons other than the grade itself — for example, a
student registered in the wrong course_id, an enrollment showing status
DROPPED when the student never withdrew, or a duplicate enrollment record
for the same student and course.

## Section 2 — Valid Disputes
A valid dispute under this policy includes: wrong course_id on an
enrollment record, a status value that does not match what actually
happened (for example DROPPED when the student did not withdraw), or two
enrollment records for the same student_id and course_id existing at
once. A dispute about the grade value itself is not covered here, see the
Grade Appeal Policy, Section 3, instead.

## Section 3 — How to File a Dispute
A dispute must reference the enrollment_id in question and describe what
is incorrect. Only the instructor assigned to the course, or an account
with role ADMIN, may investigate and correct the record, see the Grading
Permissions Policy, Section 3, for the full approval rule.

## Section 4 — Correction and Audit Trail
When an enrollment record is corrected under this policy, the original
incorrect value is not silently overwritten. The correction is logged
with the enrollment_id, the field that changed, the old value, the new
value, and the date of correction.

## Section 5 — Interaction With Re-Enrollment
If a dispute reveals that a student was incorrectly marked DROPPED, and
that incorrect drop was counted toward the drop limit in the
Re-Enrollment Policy, Section 3.2, the drop count for that course must be
corrected before any re-enrollment approval decision is made.
