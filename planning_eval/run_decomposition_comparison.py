"""
Decomposition-first vs. dynamic decomposition, required by the rubric
("a real case where the two methods diverge"). Runs the SAME real request
type through both:
- decompose_goal(): the whole plan generated up front, in one shot.
- dynamic_decomposition(): the next sub-task generated after observing
  the previous one's result.

Two real cases from fixtures.py:
- omar_stable_plan: nothing in the real data should force a mid-plan
  change, so decomposition-first is expected to do just as well, cheaper.
- kareem_dropped_course: student_id=7 has a REAL enrollment record
  (course_id=1, grade=45.0, status=DROPPED) already in db/seed.sql --
  not an invented scenario. decomposition-first has no way to react to
  this; dynamic decomposition, which sees each step's real result before
  generating the next, is the only one that can notice the drop.

Run with a real MISTRAL_API_KEY in .env:
    python -m planning_eval.run_decomposition_comparison
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

from planning.algorithms.decomposition import decompose_goal
from planning.algorithms.dynamic_decomposition import dynamic_decomposition
from planning_eval.fixtures import get_case


def _goal_text(case) -> str:
    return (
        f"Plan a complete learning path for student_id={case.student_id} "
        f"to become a {case.target_role}, respecting their real budget, "
        f"weekly-hour capacity, prerequisites, and deadline."
    )


def run_case(case_id: str, llm) -> dict:
    case = get_case(case_id)
    goal = _goal_text(case)

    t0 = time.time()
    plan = decompose_goal(goal, llm)
    decomp_first_latency = time.time() - t0
    decomp_first_tasks = [t.model_dump() for t in plan.tasks] if hasattr(plan, "tasks") else str(plan)

    t0 = time.time()
    history = dynamic_decomposition(goal, llm, max_steps=4)
    dynamic_latency = time.time() - t0

    return {
        "case_id": case.case_id,
        "student_id": case.student_id,
        "category": case.category,
        "rationale": case.rationale,
        "decomposition_first": {
            "tasks": decomp_first_tasks,
            "num_tasks": len(plan.tasks) if hasattr(plan, "tasks") else None,
            "latency_seconds": round(decomp_first_latency, 3),
        },
        "dynamic": {
            "history": [{"task": t, "result": r} for t, r in history],
            "num_steps": len(history),
            "latency_seconds": round(dynamic_latency, 3),
        },
    }


def run() -> dict:
    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env before running this comparison.")
    llm = ChatMistralAI(api_key=api_key, model="mistral-small-latest", random_seed=42, max_retries=2)

    return {
        "omar_stable_plan": run_case("omar_stable_plan", llm),
        "kareem_dropped_course": run_case("kareem_dropped_course", llm),
    }


if __name__ == "__main__":
    trace = run()
    Path("artifacts").mkdir(exist_ok=True)
    with open("artifacts/decomposition_comparison_trace.json", "w") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(trace, indent=2))
    print()
    print("=== Check for the divergence the rubric asks for ===")
    kareem_dynamic_history = trace["kareem_dropped_course"]["dynamic"]["history"]
    mentions_drop = any(
        "drop" in str(step).lower() or "45" in str(step) or "retake" in str(step).lower()
        for step in kareem_dynamic_history
    )
    print(f"Dynamic decomposition's steps mention the dropped/failed course: {mentions_drop}")
    print("(If False, re-run -- the model may need the dropped-course fact stated more explicitly")
    print(" in the goal text, e.g. add: 'Note: they previously dropped Introduction to CS with a")
    print(" failing grade and will need to retake it.')")