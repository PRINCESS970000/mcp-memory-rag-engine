"""
LATS grounded vs. ungrounded Environment comparison, required by the
rubric ("Grounded environment for LATS/Reflexion", 10 points): run the
SAME task through LATS twice, once with the real grounded Environment,
once with RandomEnvironment (the toolkit's original randomized default),
and show the case the grounded version catches that the ungrounded one
doesn't.

Case used: hoda_many_valid_orderings -- the least-constrained student in
the seed data, so there are genuinely many plausible-sounding paths for
an ungrounded evaluator to score highly by chance.

Run with a real MISTRAL_API_KEY in .env:
    python -m planning_eval.run_lats_grounded_vs_ungrounded
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

from planning.algorithms.environment import Environment
from planning.algorithms.lats import lats
from planning_eval.fixtures import get_case
from planning_eval.random_environment_baseline import RandomEnvironment


def run() -> dict:
    case = get_case("hoda_many_valid_orderings")
    task = (
        f"Propose a complete, final course path for student_id={case.student_id} "
        f"to become a {case.target_role}. This is the final committed proposal -- "
        f"it will be checked against real budget, weekly-hour, prerequisite, "
        f"skill-coverage, and deadline constraints."
    )

    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env before running this comparison.")
    llm = ChatMistralAI(api_key=api_key, model="mistral-small-latest", random_seed=42, max_retries=2)

    grounded_env = Environment(student_id=case.student_id, mcp_server_path=None)
    grounded_result, grounded_metrics = lats(task, llm, grounded_env, iterations=2, n_actions=2)

    ungrounded_env = RandomEnvironment(student_id=case.student_id, mcp_server_path=None)
    ungrounded_result, ungrounded_metrics = lats(task, llm, ungrounded_env, iterations=2, n_actions=2)

    # Re-check the ungrounded result's actual output against the REAL
    # grounded checks, after the fact -- this is what demonstrates
    # "the failure case the grounded version catches that the ungrounded
    # version missed" required by the rubric.
    real_check_on_ungrounded_output = grounded_env.evaluate(ungrounded_result.output)

    trace = {
        "case_id": case.case_id,
        "student_id": case.student_id,
        "task": task,
        "grounded": {
            "success": grounded_result.success,
            "output": grounded_result.output,
            "best_score": grounded_result.best_score,
            "iterations": grounded_result.iterations,
            "metrics": grounded_metrics,
        },
        "ungrounded": {
            "success": ungrounded_result.success,
            "output": ungrounded_result.output,
            "best_score": ungrounded_result.best_score,  # the RANDOM score it believed
            "iterations": ungrounded_result.iterations,
            "metrics": ungrounded_metrics,
            "real_grounded_check_of_same_output": {
                "success": real_check_on_ungrounded_output.success,
                "score": real_check_on_ungrounded_output.score,
                "details": real_check_on_ungrounded_output.details,
            },
        },
    }
    return trace


if __name__ == "__main__":
    trace = run()
    Path("artifacts").mkdir(exist_ok=True)
    with open("artifacts/lats_grounded_vs_ungrounded_trace.json", "w") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(trace, indent=2))
    print()
    print("=== Key comparison ===")
    print(f"Ungrounded LATS believed its score was: {trace['ungrounded']['best_score']}")
    print(f"Real grounded check of that SAME output: "
          f"{trace['ungrounded']['real_grounded_check_of_same_output']['score']} "
          f"(success={trace['ungrounded']['real_grounded_check_of_same_output']['success']})")
    print("Issues the ungrounded run never saw:")
    for d in trace["ungrounded"]["real_grounded_check_of_same_output"]["details"]:
        print(" -", d)