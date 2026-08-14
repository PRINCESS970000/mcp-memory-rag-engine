
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
