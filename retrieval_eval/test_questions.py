"""
Test question set for the BrightPeak retrieval architecture comparison.

12 questions across 3 categories, 4 each:
  - general: answerable from a single continuous passage, no section number needed.
    Naive RAG should handle these fine.
  - citation: the question names an exact section number (e.g. "3.2"). These
    identifiers don't embed distinctively, so hybrid search (vector + BM25)
    should outperform naive RAG here.
  - multi_hop: requires combining facts from two different policy documents.
    These follow the cross_refs relationships built during ingestion.
    Only agentic RAG (multiple retrieval rounds) should handle these well.

`expected_chunk_ids` is used by the eval script to check whether the retriever
actually pulled the right chunk(s), independent of whether the final generated
answer was phrased correctly. This separates retrieval accuracy from
generation accuracy when scoring.
"""

TEST_QUESTIONS = [
    # ---- GENERAL (4) ----
    {
        "id": "G1",
        "category": "general",
        "question": "When is a student allowed to withdraw from a course they're enrolled in?",
        "expected_chunk_ids": ["POL-RE-001_s2"],
    },
    {
        "id": "G2",
        "category": "general",
        "question": "What counts as valid grounds for a grade appeal?",
        "expected_chunk_ids": ["POL-GA-003_s3"],
    },
    {
        "id": "G3",
        "category": "general",
        "question": "Who is allowed to approve a re-enrollment exception after repeated drops?",
        "expected_chunk_ids": ["POL-GP-005_s3"],
    },
    {
        "id": "G4",
        "category": "general",
        "question": "What kinds of enrollment errors qualify as a valid dispute?",
        "expected_chunk_ids": ["POL-ED-004_s2"],
    },

    # ---- CITATION-HEAVY (4) ----
    {
        "id": "C1",
        "category": "citation",
        "question": "According to Section 3.2 of the Re-Enrollment Policy, who must approve re-enrollment after a student's third drop?",
        "expected_chunk_ids": ["POL-RE-001_s3.2"],
    },
    {
        "id": "C2",
        "category": "citation",
        "question": "What does Section 4 of the Grading Permissions Policy say about conflict of interest?",
        "expected_chunk_ids": ["POL-GP-005_s4"],
    },
    {
        "id": "C3",
        "category": "citation",
        "question": "Per Section 2.2 of the Grade Appeal Policy, what exactly gets recorded when an appeal is approved?",
        "expected_chunk_ids": ["POL-GA-003_s2.2"],
    },
    {
        "id": "C4",
        "category": "citation",
        "question": "What does Section 3.1 of the Certificate Reissue Policy say about a lost certificate code?",
        "expected_chunk_ids": ["POL-CR-002_s3.1"],
    },

    # ---- MULTI-HOP / DECOMPOSITION (4) ----
    {
        "id": "M1",
        "category": "multi_hop",
        "question": "A student has been dropped from the same course three times and wants to re-enroll. Exactly who is allowed to approve that?",
        "expected_chunk_ids": ["POL-RE-001_s3.2", "POL-GP-005_s3"],
    },
    {
        "id": "M2",
        "category": "multi_hop",
        "question": "A student's grade was corrected after their certificate was already issued. Does the certificate get reissued?",
        "expected_chunk_ids": ["POL-GA-003_s2.2", "POL-CR-002_s4"],
    },
    {
        "id": "M3",
        "category": "multi_hop",
        "question": "A student was incorrectly marked DROPPED by mistake, and that error was counted toward their drop limit for the course. What has to happen before any re-enrollment decision is made?",
        "expected_chunk_ids": ["POL-ED-004_s5", "POL-RE-001_s3"],
    },
    {
        "id": "M4",
        "category": "multi_hop",
        "question": "An instructor wants to approve a grade appeal for a student who is also a TA teaching alongside them. Can the instructor approve it?",
        "expected_chunk_ids": ["POL-GA-003_s5", "POL-GP-005_s4"],
    },
]
