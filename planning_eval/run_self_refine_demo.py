"""
Real Self-Refine demo on its actual designed sub-task: refining the
student-facing explanation text (not the path-proposal comparison used in
run_reflexion_vs_selfrefine.py). Produces real draft -> critique ->
revision text for the demo transcript.

Run with a real MISTRAL_API_KEY in .env:
    python -m planning_eval.run_self_refine_demo
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
from planning.algorithms.self_refine import reflect_and_refine
from planning_eval.fixtures import get_case


def run() -> dict:
    case = get_case("omar_stable_plan")
    environment = Environment(student_id=case.student_id, mcp_server_path=None)
    data = environment.get_catalog_data()
    courses_by_id = {c["course_id"]: c for c in data["courses"]}

    # A deliberately imperfect draft: correct courses, but wrong total
    # (a plausible real LLM arithmetic slip) -- this is what
    # grounded_path_checks() is designed to catch.
    path_ids = [7, 12]
    path_courses = [courses_by_id[cid] for cid in path_ids]
    real_total = sum(c["price"] for c in path_courses)
    draft = (
        f"To become a {case.target_role}, I recommend starting with "
        f"{path_courses[0]['title']} and {path_courses[1]['title']}. "
        f"Together these cost about ${real_total + 150:.2f} and will build "
        f"your foundational skills."
    )

    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env before running this demo.")
    llm = ChatMistralAI(api_key=api_key, model="mistral-small-latest", random_seed=42, max_retries=2)

    result = reflect_and_refine(
        goal=f"Explain this recommended path to a student becoming a {case.target_role}",
        draft=draft,
        path_courses=path_courses,
        all_courses=data["courses"],
        total_price=real_total,
        llm=llm,
    )

    return {
        "case_id": case.case_id,
        "draft": draft,
        "real_total_price": real_total,
        "grounded_issues_found": result.grounded_issues,
        "ungrounded_critique": result.critique,
        "revised": result.revised,
        "metrics": result.metrics,
    }


if __name__ == "__main__":
    trace = run()
    Path("artifacts").mkdir(exist_ok=True)
    with open("artifacts/self_refine_explanation_demo_trace.json", "w") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(trace, indent=2))