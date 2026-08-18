"""
Self-Refine vs. Reflexion, on the same sub-task: propose a complete
learning path satisfying every constraint for a real student.

Why the same sub-task for both, when self_refine.py itself is routed to a
*different* sub-task (the student-facing explanation text)? To produce a
fair number in the comparison table ("Pick what your system actually
ships with, per sub-task type, and justify each choice against the
table"), this script runs a single-pass baseline shaped exactly like
Self-Refine (one draft, one grounded critique via the real Environment,
one revision) against the full Reflexion multi-trial loop, on
fixtures.salma_tight_constraints -- the case where the constraints
genuinely interact, so it's the deciding case for whether Self-Refine's
single revision is enough or Reflexion's cross-trial memory is needed.

Run with a real MISTRAL_API_KEY in .env:
    python -m planning_eval.run_reflexion_vs_selfrefine
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

from planning.algorithms.environment import Environment
from planning.algorithms.reflexion import reflexion
from planning_eval.fixtures import get_case


def single_pass_baseline(environment: Environment, initial_attempt_fn) -> dict:
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
            "final_score": draft_feedback.score, "latency_s": round(time.time() - t0, 3),
        }

    # One revision informed by the grounded critique -- drop the last
    # course, a simple deterministic revision policy (not an LLM call),
    # to isolate "does one more pass help at all".
    revised_ids = draft_ids[:-1]
    revised_feedback = environment.evaluate(revised_ids)
    return {
        "success": revised_feedback.success,
        "final_course_ids": revised_ids,
        "attempts": 2,
        "final_score": revised_feedback.score,
        "latency_s": round(time.time() - t0, 3),
        "details": revised_feedback.details,
    }


def run() -> dict:
    case = get_case("salma_tight_constraints")
    environment = Environment(student_id=case.student_id, mcp_server_path=None)
    catalog_data = environment.get_catalog_data()

    all_course_ids = [c["course_id"] for c in catalog_data["courses"]]
    overambitious_draft = all_course_ids[:5]

    baseline_result = single_pass_baseline(environment, initial_attempt_fn=lambda: overambitious_draft)

    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env before running this comparison.")
    llm = ChatMistralAI(api_key=api_key, model="mistral-small-latest", random_seed=42, max_retries=2)

    reflexion_result = reflexion(environment=environment, catalog_data=catalog_data, llm=llm, max_trials=3, memory_size=3)

    return {
        "case_id": case.case_id,
        "student_id": case.student_id,
        "self_refine_single_pass": baseline_result,
        "reflexion_multi_trial": {
            "success": reflexion_result.success,
            "final_course_ids": reflexion_result.best_course_ids,
            "num_trials": len(reflexion_result.trials),
            "final_score": max((t.feedback.score for t in reflexion_result.trials), default=0.0),
            "reflections": [t.reflection for t in reflexion_result.trials if t.reflection],
            "metrics": reflexion_result.metrics,
        },
    }


if __name__ == "__main__":
    trace = run()
    Path("artifacts").mkdir(exist_ok=True)
    with open("artifacts/self_refine_vs_reflexion_trace.json", "w") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(trace, indent=2))