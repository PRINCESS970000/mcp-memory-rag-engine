
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict

from ..tool_args import call_real_tool


class DynamicDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool
    next_task: str
    expected_tool: str | None = None


def dynamic_decomposition(goal: str, llm: BaseChatModel, max_steps: int = 4) -> list[tuple[str, str]]:
    history: list[tuple[str, str]] = []
    for step in range(max_steps):
        observation = "\n".join(f"{task}: {result}" for task, result in history) or "None"
        decision = llm.with_structured_output(
            DynamicDecision,
            method="json_schema",
        ).invoke([
            (
                "system",
                "You are an adaptive planner for BrightPeak Academy's Learning Path "
                "Planning agent. Use prior observations -- including real tool results "
                "such as failed prerequisite checks or over-budget searches -- before "
                "deciding what comes next. Set expected_tool to the real tool name "
                "(get_student_profile, get_role_requirements, search_courses, "
                "check_prerequisites, save_learning_goal, enroll_student) if the next "
                "task is a lookup/write, or null if it requires reasoning.",
            ),
            ("human", f"""Goal: {goal}
Completed work and observations:
{observation}

Decide the single best next task. Set done to true only when the goal is met.
When done is true, use an empty string for next_task."""),
        ], temperature=0.1)
        if decision.done:
            break
        task = decision.next_task.strip()
        if not task:
            raise ValueError(f"Dynamic planner omitted next_task at step {step + 1}")

        if decision.expected_tool:
            # Grounded: the real tool result becomes the observation the
            # NEXT decision step reasons over, not an LLM guess at one.
            result = call_real_tool(decision.expected_tool, llm, goal, task, observation)
        else:
            response = llm.invoke([
                ("system", "Execute the next adaptive sub-task using the observations provided."),
                ("human", f"Goal: {goal}\nNext task: {task}\nPrior observations:\n{observation}"),
            ], temperature=0.2)
            result = response.content
            if not isinstance(result, str) or not result.strip():
                raise RuntimeError("The chat model returned an empty or unsupported response")
            result = result.strip()

        history.append((task, result))
    return history