---
policy_type: certificate_reissue
document_id: POL-CR-002
last_reviewed_date: 2026-02-01
version: 1.0
---

# BrightPeak Certificate Reissue Policy

## Section 1 — Eligibility
A certificate may only exist for an enrollment whose status is COMPLETED
and whose grade is recorded (not null). An enrollment with status
ENROLLED or DROPPED is never eligible for a certificate. Each enrollment
may have at most one certificate, since certificate records are uniquely
tied to a single enrollment_id.

## Section 2 — Standard Issuance
A certificate is created once an instructor or admin records a grade that
brings an enrollment's status to COMPLETED. The certificate_code is
generated once, at creation, and does not change afterward.

## Section 3 — Lost or Duplicate Certificate Requests

### Section 3.1 — Lost Certificate Code
If a student loses their certificate_code, they submit a reissue request
identifying the enrollment_id. The system looks up the existing
certificate record for that enrollment_id and returns the original
certificate_code unchanged. A new code is never generated for a lost-code
request.

### Section 3.2 — Duplicate Prevention
Because each enrollment_id can be linked to only one certificate, a
duplicate reissue request must return the existing certificate rather
than create a second record.

## Section 4 — Certificates After a Grade Correction
If a grade is corrected after a certificate has already been issued, see
the Grade Appeal Policy, Section 2 for how the correction is logged. The
existing certificate_code is not changed and no new certificate is
issued; the correction is recorded as an audit note against the same
enrollment_id.

## Section 5 — Certificates and Repeated Enrollment
If a student was previously DROPPED from a course and later completed it
on a later attempt, only the completed attempt's enrollment_id is
eligible for a certificate, see the Re-Enrollment Policy, Section 3, for
how repeated drops on the same course are tracked.
