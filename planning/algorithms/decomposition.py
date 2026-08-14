

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict

from ..models import Plan
from ..tool_args import call_real_tool

try:
    from .routing import route_and_execute_subtask
except ImportError:  # pragma: no cover - person 2's file not merged yet
    route_and_execute_subtask = None

from .environment import Environment


GROUNDING_DIRECTIVE = """STRICT GROUNDING RULE (do not violate):
Base your answer ONLY on the literal data in "Prerequisite outputs" below --
this is real data from the database/tools, not a hypothetical. Specifically:
  - Read exact field values (e.g. skill_tags, status, price) verbatim. Do
    NOT infer a skill from a course title if it isn't literally in that
    course's skill_tags. Do NOT treat status="ENROLLED" as completed.
  - Do NOT invent course names, ids, prices, dates, or prerequisites that
    are not literally present in the prerequisite outputs.
  - If a real course/result was found in the prerequisite outputs, your
    answer must use THAT course -- never substitute a placeholder
    ("Course A", "Course B"...) when a real one was already given to you.
  - If the given data is insufficient to complete part of the task, say so
    explicitly instead of filling the gap with a plausible-sounding guess."""


PLANNER_SYSTEM = """You are the decomposition planner for BrightPeak Academy's
Learning Path Planning agent. A student wants a course plan toward a target
job role, under real constraints: weekly hours available, budget, course
prerequisites, and course start/end dates.

Produce a small executable DAG (3-8 tasks), not a prose checklist. For every
task, set expected_tool to the name of the real tool that resolves it, or
null if the task requires reasoning rather than a lookup/write:
  - get_student_profile     : read the student's completed/enrolled courses
  - get_role_requirements   : read the skill tags required by the target role
  - search_courses          : find candidate courses by skill/budget/hours/date
  - check_prerequisites     : verify a specific course's prerequisites are met
  - save_learning_goal      : persist the student's weekly hours/budget/target
  - enroll_student           : commit the student into a specific course
  - null (reasoning)        : gap analysis, filtering by constraints,
                               choosing/ordering courses, writing the summary

When expected_tool is null, also set category to steer which planning
algorithm handles it (planning/routing.py) -- use EXACTLY one of these
three literal strings (the router matches them as substrings, so close
paraphrases like "course_sequencing" will NOT match):
  - "deterministic_parsing" : a single correct answer, no real branching
                               (e.g. gap analysis, budget/hours filtering)
  - "select_courses"        : several valid orderings must be compared
                               before committing (e.g. ranking/sequencing
                               candidate courses)
  - "" (leave blank)        : the highest-stakes reasoning step, where a
                               wrong choice is expensive to undo (e.g.
                               choosing the final course to commit to)

The plan must end with exactly one synthesis task (expected_tool: null,
category: "deterministic_parsing") that summarizes the final path for the
student.

IMPORTANT ON DATES: the goal may state a target completion deadline (e.g.
"target 2026-11-01"). That deadline is NOT a course start-date filter --
never translate it into a "only show courses starting after this date"
constraint. A candidate-search task should filter by skill/budget/hours
only; the deadline is checked later, when sequencing/committing courses,
by comparing each course's own end_date against it."""


class PlannedTask(BaseModel):
    """Wire schema; richer semantic constraints are applied by the Task domain model."""

    model_config = ConfigDict(extra="forbid")

    id: str
    instruction: str
    depends_on: list[str]
    expected_tool: str | None = None
    category: str = ""


class GeneratedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    tasks: list[PlannedTask]


def decompose_goal(goal: str, llm: BaseChatModel) -> Plan:
    generated = llm.with_structured_output(
        GeneratedPlan,
        method="json_schema",
    ).invoke([
        ("system", PLANNER_SYSTEM),
        ("human", f"""Decompose this request into 3-8 tasks: {goal!r}
Use short task ids such as t1. Dependencies may refer only to tasks in the plan.
Preserve the supplied goal exactly in the plan's goal field."""),
    ], temperature=0.1)
    # The caller's goal remains authoritative even if the model paraphrases it.
    payload = generated.model_dump()
    payload["goal"] = goal
    return Plan.model_validate(payload)


def execute_plan(plan: Plan, llm: BaseChatModel, environment: Environment | None = None, max_workers: int = 4) -> tuple[dict[str, str], dict[str, dict]]:
    """Returns (outputs, metrics_by_task). metrics_by_task only has entries
    for tasks routed through PS/ToT/LATS (routing.py) -- tool-tasks and the
    plain-LLM fallback don't produce per-algorithm metrics."""
    # Person 3 replaces this default with a grounded Environment; the
    # toolkit's randomized one is only a placeholder until then (LATS
    # needs *some* Environment instance to run at all).
    environment = environment or Environment()
    outputs: dict[str, str] = {}
    metrics_by_task: dict[str, dict] = {}
    for batch in plan.execution_batches():
        prompts: dict[str, str] = {}
        tool_tasks: dict[str, str] = {}     # task_id -> context, resolved via a real MCP tool
        routed_tasks: dict[str, str] = {}   # task_id -> context, resolved via PS/ToT/LATS
        for task_id in batch:
            task = plan.task(task_id)
            context = "\n\n".join(
                f"OUTPUT FROM {dependency}:\n{outputs[dependency]}"
                for dependency in task.depends_on
            ) or "No prerequisite outputs."

            if task.expected_tool:
                tool_tasks[task_id] = context
            elif route_and_execute_subtask is not None:
                routed_tasks[task_id] = context
            else:
                prompts[task_id] = f"""Overall goal: {plan.goal}
                Current task: {task.instruction}
                Prerequisite outputs:
                {context}
                Complete only the current task. Be concrete and concise. Do not invent sources."""

        # Grounded sub-tasks: call the real tool. Run sequentially (not in
        # the thread pool below) since several of these are real DB writes
        # (enroll_student, save_learning_goal) and shouldn't race each other.
        for task_id, context in tool_tasks.items():
            task = plan.task(task_id)
            outputs[task_id] = call_real_tool(task.expected_tool, llm, plan.goal, task.instruction, context)

        # Reasoning-only sub-tasks: person 2's routing.py picks PS/ToT/LATS
        # per task.category. route_and_execute_subtask returns (result,
        # metrics) -- metrics are kept per-task for the run trace, not
        # discarded, since person 3's comparison table needs them.
        for task_id, context in routed_tasks.items():
            task = plan.task(task_id)
            subtask = {
                "description": (
                    f"{GROUNDING_DIRECTIVE}\n\n{task.instruction}\n\n"
                    f"Prerequisite outputs (the ONLY source of truth for this task):\n{context}"
                ),
                "category": task.category,
            }
            result, metrics = route_and_execute_subtask(subtask, llm, environment)
            content = result if isinstance(result, str) else str(result)
            if not content.strip():
                raise RuntimeError(f"route_and_execute_subtask returned an empty result for {task_id!r}")
            outputs[task_id] = content.strip()
            metrics_by_task[task_id] = metrics  # kept for the run trace (planning_eval/'s table)

        # Fallback: only reached if routing.py isn't on the path at all.
        if prompts:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(prompts))) as pool:
                futures = {
                    pool.submit(
                        llm.invoke,
                        [
                            ("system", "You execute one node in a validated task DAG."),
                            ("human", prompt),
                        ],
                        temperature=0.2,
                    ): task_id
                    for task_id, prompt in prompts.items()
                }
                for future in as_completed(futures):
                    content = future.result().content
                    if not isinstance(content, str) or not content.strip():
                        raise RuntimeError("The chat model returned an empty or unsupported response")
                    outputs[futures[future]] = content.strip()

    return outputs, metrics_by_task


def final_output(plan: Plan, outputs: dict[str, str]) -> str:
    terminals = plan.terminal_tasks()
    if len(terminals) != 1:
        raise ValueError(f"Expected exactly one terminal synthesis task, found {terminals}")
    return outputs[terminals[0]]