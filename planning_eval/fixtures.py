"""
Fixed test suite for the Adaptive Learning Path Planning agent.

FROZEN once evaluation starts. Per the lab guardrails: "Keep your planning
test suite fixed once you start evaluating. Changing test cases between
runs invalidates your comparison table." Do not edit the CASES list below
after the first real run_eval.py execution whose traces get used in the
comparison table -- add a new case as a new entry instead of editing an
existing one, and note the addition in the README changelog.

Each case is a real student already in db/seed.sql (BrightPeak Academy),
not an invented scenario, so every constraint (budget, weekly hours,
prerequisites already completed, deadline) is real data the grounded
Environment actually checks against.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    student_id: int
    student_name: str
    target_role: str
    category: str  # which required rubric scenario this case demonstrates
    rationale: str


CASES: list[EvalCase] = [
    EvalCase(
        case_id="omar_stable_plan",
        student_id=1,
        student_name="Omar Khaled",
        target_role="Data Scientist",
        category="decomposition_first_favored",
        rationale=(
            "Budget 700, 10 hrs/week, deadline 2027-02-01 (roomy). Two "
            "prerequisites already COMPLETED, one already ENROLLED with no "
            "recorded failure. Nothing in this student's real data should "
            "force a mid-plan replan, so committing to the whole plan "
            "upfront (decomposition-first) is cheaper and just as good as "
            "reacting step by step."
        ),
    ),
    EvalCase(
        case_id="kareem_dropped_course",
        student_id=7,
        student_name="Kareem Reda",
        target_role="Software Engineer",
        category="dynamic_decomposition_favored",
        rationale=(
            "Real enrollment record: course_id=1, grade=45.0, "
            "status=DROPPED. A plan generated up front (decomposition-first) "
            "has no way to react to this -- it would blindly assume course 1 "
            "is satisfied or ignore it. Dynamic decomposition, which "
            "observes each sub-task's real result before generating the "
            "next one, is the only method that can notice the drop and "
            "insert a retake before anything depending on it."
        ),
    ),
    EvalCase(
        case_id="hoda_many_valid_orderings",
        student_id=6,
        student_name="Hoda Mansour",
        target_role="ML Engineer",
        category="lookahead_search_needed",
        rationale=(
            "Budget 1000, 15 hrs/week, deadline 2027-03-01 -- the least "
            "constrained student in the seed data, meaning many different "
            "course orderings are individually valid. Picking one without "
            "comparing alternatives (Plan-and-Solve) risks a locally "
            "reasonable but globally worse ordering; Tree of Thoughts can "
            "compare several before committing, and the final commit is "
            "routed to LATS since a wrong final proposal is expensive to "
            "unwind for a real student."
        ),
    ),
    EvalCase(
        case_id="salma_tight_constraints",
        student_id=8,
        student_name="Salma Farouk",
        target_role="Software Engineer",
        category="reflexion_needed",
        rationale=(
            "Budget 500, 8 hrs/week, deadline 2026-12-01 -- the tightest "
            "combination of constraints in the seed data. A single attempt "
            "predictably fixes one violated constraint (e.g. budget) while "
            "breaking another (e.g. skill coverage), which is exactly the "
            "case Self-Refine (single pass) can't handle but Reflexion's "
            "cross-trial memory can: each trial's grounded feedback about "
            "which constraint broke becomes the next trial's input."
        ),
    ),
]


def get_case(case_id: str) -> EvalCase:
    for case in CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"No eval case with id {case_id!r}")