import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # task_decomposition_and_planning/
sys.path.insert(0, str(ROOT))

from planning_lab.algorithms.routing import route_and_execute_subtask
from planning_lab.algorithms import Environment
from langchain_mistralai import ChatMistralAI


if not os.environ.get("MISTRAL_API_KEY"):
    raise ValueError(" MISTRAL_API_KEY is not set in environment variables!")


llm = ChatMistralAI(model="mistral-small-latest", temperature=0.2)
# student_id=1 is Omar Khaled in db/seed.sql, with a real learning_goal
# targeting Data Scientist -- matches what most test_subtasks below describe.
_mcp_server_path = str((ROOT.parent / "mcp_server").resolve())
env = Environment(student_id=1, mcp_server_path=_mcp_server_path)


test_subtasks = [
    # --- Plan-and-Solve (PS) ---
    {"category": "extract_parse", "description": "Extract and parse user constraints from the text: 'I am a 2nd year CS student with $300 budget and 8 hours free per week. My goal is to become a Data Scientist.' Output a structured JSON object containing budget, weekly_hours, current_level, and target_role."},
    {"category": "format", "description": "Format the following list of approved courses [Python Basics, Machine Learning 101, SQL for Data Science] into a clean Markdown table with estimated duration and weekly workload."},
    {"category": "calculate", "description": "Calculate the total cost and total weeks needed for a sequence of 3 courses costing $100 (4 weeks), $150 (6 weeks), and $50 (2 weeks). Check if total cost exceeds a $350 budget."},
    
    # --- Tree of Thoughts (ToT) ---
    {"category": "rank_sequence", "description": "Given a student targeting Data Scientist role who already knows Python, propose two candidate course sequence options to learn Data Science. Compare prerequisites for Machine Learning vs. Deep Learning."},
    {"category": "rank_sequence", "description": "Rank three potential elective paths for a student: Path A (Focus on MLOps), Path B (Focus on Computer Vision), Path C (Focus on NLP). Evaluate feasibility assuming a 10 hours/week constraint."},
    {"category": "rank_sequence", "description": "Evaluate whether a student should take 'Advanced Statistics' before 'Data Mining' or concurrently, considering they have 6 hours available per week."},
    
    # --- LATS ---
    {"category": "schedule_optimize", "description": "Optimize and generate a final 12-week course schedule for a student aiming for Data Scientist role. Budget: $400, Available time: 10 hrs/week. Ensure no course prerequisite is violated and no budget overflow occurs."},
    {"category": "schedule_optimize", "description": "Resolve a schedule conflict where Course A (Intro to AI) and Course B (Data Structures) both run in September and require 8 hours/week each, but the student only has 10 hours total available per week."},
    {"category": "schedule_optimize", "description": "Generate a complete multi-semester Learning Path for a complete beginner targeting Data Analyst role within a strict budget of $200 and max 6 hours/week. Test and verify against environment feedback."}
]

def run():
    all_metrics = []
    print("\n === STARTING MISTRAL RUNNER TESTS ===\n")
    
    for idx, subtask in enumerate(test_subtasks, 1):
        print("--------------------------------------------------")
        print(f"▶ Test #{idx} [{subtask['category']}]")
        print(f"Prompt: {subtask['description'][:80]}...")
        
        # Router
        result, metrics = route_and_execute_subtask(subtask, llm, env)
        
        print(f"\n[ROUTER DECISION]: Routed to -> {metrics.get('routed_algorithm')}")
        print(f"[RESULT OUTPUT]:\n{result}")
        print(f"[METRICS]: {metrics}\n")
        
        all_metrics.append(metrics)


    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/execution_traces.json", "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)
        
    print("✅ Finished! All traces saved to artifacts/execution_traces.json")

if __name__ == "__main__":
    run()