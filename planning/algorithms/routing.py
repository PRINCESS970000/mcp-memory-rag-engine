"""
Routing logic: decides which of Plan-and-Solve, Tree of Thoughts, or LATS
handles a given DAG sub-task, based on the sub-task's real shape --
not a fixed assignment, and not "whichever sounds most sophisticated."

- Plan-and-Solve: deterministic/logical sub-tasks with no real branching
  -- extracting a field, formatting a summary, parsing a lookup result.
  There's nothing to compare between alternatives, so a single
  generate-and-execute pass is both cheaper and just as correct as a
  search (see the Overall Statistics table in the main README: PS costs
  ~1 LLM call vs. ToT's ~9 for no accuracy gain on this task shape).

- Tree of Thoughts: sub-tasks that need comparing several alternatives
  before committing, where committing to the first plausible option risks
  a locally-reasonable but globally worse choice -- ranking candidate
  courses by urgency/prerequisite readiness, sequencing a course set into
  an order. Self-evaluating and pruning branches costs more calls than
  Plan-and-Solve but catches orderings PS's single pass would miss.

- LATS: the sub-task where a wrong choice is the most expensive to
  undo -- proposing the FINAL committed course path, the one that
  actually gets checked against real budget/hours/prerequisite/deadline
  constraints via Environment.evaluate(). Everything else (deterministic
  parsing, sequencing) is routed elsewhere specifically so LATS's higher
  cost (~10 LLM calls, see planning_eval/) is only paid on the one
  sub-task where external grounded feedback is worth it.

Category keywords below come directly from the task categories
decomposition.py's planner prompt is instructed to assign
(deterministic_parsing / select_courses / ...), not from arbitrary
string matching -- the fallback to LATS is deliberate: any sub-task not
explicitly recognized as cheap-and-deterministic or comparison-needing is
treated as high-stakes by default, which is the safer failure mode.
"""

from typing import Dict, Any, Tuple
from langchain_core.language_models.chat_models import BaseChatModel

from .plan_and_solve import plan_and_solve
from .tree_of_thoughts import tree_of_thoughts
from .lats import lats
from .environment import Environment


def route_and_execute_subtask(
    subtask: Dict[str, Any],
    llm: BaseChatModel,
    environment: Environment
) -> Tuple[Any, Dict[str, Any]]:
    
    task_description = subtask.get("description", "")
    task_category = subtask.get("category", "").lower()

    if any(k in task_category for k in ["extract", "parse", "format", "deterministic"]):
        algorithm_choice = "Plan-and-Solve"
        result, metrics = plan_and_solve(task_description, llm, task_type="deterministic_parsing")

    elif any(k in task_category for k in ["rank", "sequence", "prerequisite", "select_courses"]):
        algorithm_choice = "Tree of Thoughts"
        result, metrics = tree_of_thoughts(task_description, llm, depth=2, beam_width=2, task_type="course_sequencing")

    else:
        algorithm_choice = "LATS"
        result, metrics = lats(task_description, llm, environment, iterations=2, n_actions=2, task_type="schedule_optimization")

    metrics["routed_algorithm"] = algorithm_choice
    
    print(f"\n[ROUTER] Assigned Subtask to -> {algorithm_choice}")
    print(f"[OUTPUT] -> {result}")
    
    return result, metrics