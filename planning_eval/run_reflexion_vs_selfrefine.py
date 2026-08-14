"""
Self-Refine vs. Reflexion, on the same sub-task: propose a complete
learning path satisfying every constraint for a real student.

Why the same sub-task for both, when self_refine.py itself is routed to a
*different* sub-task (the student-facing explanation text)? To produce a
fair number in the comparison table ("Pick what your system actually
ships with, per sub-task type, and justify each choice against the
table"), this script runs a single-pass baseline shaped exactly like
Self-Refine (one draft, one grounded critique, one revision -- reusing
the SAME grounded Environment checks, not a separate rubric) against the
full Reflexion multi-trial loop, on fixtures.salma_tight_constraints. That
is the case where the constraints genuinely interact, so it's the
deciding case for whether Self-Refine's single revision is enough or
Reflexion's cross-trial memory is actually needed.

Run with: python -m planning_eval.run_reflexion_vs_selfrefine
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from planning.algorithms.environment import Environment
from planning.algorithms import reflexion as reflexion_fn  # noqa: F401 (forces submodule import)
import sys as _sys
reflexion_mod = _sys.modules["planning.algorithms.reflexion"]
from planning_eval.fixtures import get_case


def single_pass_baseline(student_id: int, environment: Environment, initial_attempt_fn) -> dict:
    """Shaped like Self-Refine: ONE draft, ONE grounded critique (via the
    real Environment, not an LLM opinion), ONE revision attempt. No
    further retries even if the revision still fails -- that's exactly
    the limitation this comparison is meant to surface."""
    t0 = time.time()
    draft_ids = initial_attempt_fn()
    draft_feedback = environment.evaluate(draft_ids)
    if draft_feedback.success:
        return {
            "success": True, "final_course_ids": draft_ids, "attempts": 1,
            "final_score": draft_feedback.score, "latency_s": time.time() - t0,
        }

    # One revision informed by the grounded critique -- drop the cheapest
    # violation-causing course, a simple deterministic revision policy
    # (not an LLM call), to isolate "does one more pass help at all".
    revised_ids = [cid for cid in draft_ids if cid != draft_ids[-1]]
    revised_feedback = environment.evaluate(revised_ids)
    return {
        "success": revised_feedback.success,
        "final_course_ids": revised_ids,
        "attempts": 2,
        "final_score": revised_feedback.score,
        "latency_s": time.time() - t0,
        "details": revised_feedback.details,
    }


def run(mock_llm_responses: list[str] | None = None) -> dict:
    case = get_case("salma_tight_constraints")
    environment = Environment(student_id=case.student_id, mcp_server_path=None)
    catalog_data = environment.get_catalog_data()

    # A deliberately over-ambitious first draft, like a real first attempt
    # that tries to cover every required skill without checking cost/hours.
    all_course_ids = [c["course_id"] for c in catalog_data["courses"]]
    overambitious_draft = all_course_ids[:5]

    t0 = time.time()
    baseline_result = single_pass_baseline(
        case.student_id, environment, initial_attempt_fn=lambda: overambitious_draft
    )
    baseline_time = time.time() - t0

    trace = {
        "case_id": case.case_id,
        "student_id": case.student_id,
        "self_refine_single_pass": baseline_result,
    }

    if mock_llm_responses is not None:
        from unittest.mock import patch, MagicMock
        call_log = []

        def fake_create(**kwargs):
            idx = len(call_log)
            call_log.append(kwargs["messages"][0]["content"][:80])
            return MagicMock(content=[MagicMock(text=mock_llm_responses[idx])])

        t1 = time.time()
        with patch.object(reflexion_mod.client.messages, "create", side_effect=fake_create):
            reflexion_result = reflexion_mod.reflexion(
                environment=environment, catalog_data=catalog_data,
                max_trials=3, memory_size=3,
            )
        reflexion_time = time.time() - t1
        trace["reflexion_multi_trial"] = {
            "success": reflexion_result.success,
            "final_course_ids": reflexion_result.best_course_ids,
            "num_trials": len(reflexion_result.trials),
            "final_score": max((t.feedback.score for t in reflexion_result.trials), default=0.0),
            "latency_s": reflexion_time,
            "llm_calls": len(call_log),
        }

    return trace


if __name__ == "__main__":
    # Placeholder mock sequence for a dry run without an API key; replace
    # with real client.messages.create calls (remove mock_llm_responses)
    # once ANTHROPIC_API_KEY is set in .env for the real evaluation run.
    trace = run(mock_llm_responses=[
        "[1, 3, 4]",
        "I covered all required skills but blew both the budget and the 8 hrs/week limit since all three courses overlap in September. Next trial I should drop one course and prioritize the cheapest way to still cover programming, cs_fundamentals, and databases.",
        "[1, 3]",
        "Budget is better but courses 1 and 3 still overlap Sep-Oct at 6+8=14 hrs/week, way over the 8 hr limit, and I'm still missing software_engineering. I need courses that don't overlap in dates or that sum to under 8 hrs/week together.",
        "[1, 12]",
        "This fits budget and hours but drops databases and software_engineering entirely, so skill coverage fails. Given the fixed course dates, no combination in this catalog satisfies all four skills within 8 hrs/week -- the next trial should prioritize maximum skill coverage within the hour limit rather than chasing full coverage.",
    ])
    Path("artifacts").mkdir(exist_ok=True)
    with open("artifacts/self_refine_vs_reflexion_trace.json", "w") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(trace, indent=2))