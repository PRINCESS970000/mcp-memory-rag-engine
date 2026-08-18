"""
Reflexion for the Adaptive Learning Path Planning agent.

Sub-task routed here: propose ONE COMPLETE learning path (ordered list of
course_ids) that satisfies every constraint together -- prerequisites,
budget, weekly hours, schedule, skill coverage, and deadline. This is
exactly the sub-task where a single retry (Self-Refine) isn't enough: the
constraints interact. Dropping an expensive course to fix the budget can
break skill coverage; adding a course to cover a missing skill can blow the
weekly-hours limit. The agent needs to learn across multiple attempts
within the same run, carrying forward what specifically went wrong.

Adapted from the toolkit's algorithms/reflexion.py:
- Same trial loop, same capped episodic memory buffer (memory[-memory_size:]).
- LLM client: uses `llm: BaseChatModel` and `llm.invoke([...])`, the same
  convention plan_and_solve.py / tree_of_thoughts.py / lats.py already use
  (ChatMistralAI in practice), instead of a separate Anthropic client --
  keeps one consistent LLM provider across the whole planning/ package.
- The toolkit's environment.evaluate() takes a raw string `attempt`. Ours
  (Environment.evaluate) accepts either a free-text string (what LATS
  passes) or a plain list[int] of course_ids (what this file passes
  directly) -- the grounded checks apply identically either way.
"""

import json
import re
import time
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from ..models import EnvironmentFeedback
from .environment import Environment


@dataclass
class ReflexionTrial:
    number: int
    course_ids: list[int]
    feedback: EnvironmentFeedback
    reflection: str | None = None


@dataclass
class ReflexionResult:
    success: bool
    best_course_ids: list[int]
    trials: list[ReflexionTrial]
    memory: list[str]
    metrics: dict


def _format_catalog(courses: list[dict]) -> str:
    lines = []
    for c in courses:
        lines.append(
            f"- id={c['course_id']} '{c['title']}' price={c['price']} "
            f"weekly_hours={c['weekly_hours']} dates={c['start_date']}..{c['end_date']} "
            f"skills={c['skill_tags']}"
        )
    return "\n".join(lines)


def _parse_course_ids(text: str) -> list[int]:
    match = re.search(r"\[[\d,\s\"']*\]", text)
    if not match:
        raise ValueError(f"Could not find a JSON list of course_ids in model output: {text!r}")
    return [int(course_id) for course_id in json.loads(match.group(0))]


def _invoke(llm: BaseChatModel, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
    """Shared call helper matching plan_and_solve.py's exact convention,
    so every algorithm in this package produces metrics in the same shape
    for planning_eval/'s comparison table."""
    start = time.time()
    response = llm.invoke([
        ("system", system_prompt),
        ("human", user_prompt),
    ])
    latency = round(time.time() - start, 3)

    if not isinstance(response.content, str) or not response.content.strip():
        raise RuntimeError("Reflexion: the chat model returned an empty or unsupported response.")

    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
        usage = response.response_metadata["token_usage"]
        token_usage["prompt_tokens"] = usage.get("prompt_tokens", 0)
        token_usage["completion_tokens"] = usage.get("completion_tokens", 0)
        token_usage["total_tokens"] = usage.get(
            "total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        )

    return response.content.strip(), {"latency_seconds": latency, **token_usage}


def reflexion(
    environment: Environment,
    catalog_data: dict,
    llm: BaseChatModel,
    max_trials: int = 3,
    memory_size: int = 3,
) -> ReflexionResult:
    """catalog_data: the dict returned by environment.get_catalog_data()
    -- pass it in once so this function doesn't re-fetch it every trial."""
    if max_trials < 1 or memory_size < 1:
        raise ValueError("max_trials and memory_size must be positive")

    goal = catalog_data["learning_goal"]
    catalog_text = _format_catalog(catalog_data["courses"])
    completed_text = ", ".join(str(c) for c in catalog_data["completed_course_ids"]) or "none"
    required_skills_text = ", ".join(catalog_data["required_skills"])

    memory: list[str] = []
    trials: list[ReflexionTrial] = []
    best_course_ids: list[int] = []
    best_score = -1.0
    metrics = {"algorithm": "Reflexion", "llm_calls": 0, "prompt_tokens": 0,
               "completion_tokens": 0, "total_tokens": 0, "latency_seconds": 0.0}

    def _accumulate(call_metrics: dict) -> None:
        metrics["llm_calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            metrics[k] += call_metrics[k]
        metrics["latency_seconds"] = round(metrics["latency_seconds"] + call_metrics["latency_seconds"], 3)

    for number in range(1, max_trials + 1):
        recalled = "\n".join(f"- {item}" for item in memory[-memory_size:]) or "- No prior trials."
        raw, call_metrics = _invoke(
            llm,
            system_prompt="You propose complete learning-path course sequences for BrightPeak Academy students.",
            user_prompt=f"""Propose a complete course path for this student.

Budget: {goal['budget']}, weekly hours available: {goal['weekly_hours_available']}, target date: {goal['target_date']}
Required skills: {required_skills_text}
Already completed courses: {completed_text}

Available courses:
{catalog_text}

Lessons from previous failed attempts:
{recalled}

Respond with ONLY a JSON list of course_ids in the order the student should
take them, e.g. [3, 7, 12]. Apply the lessons above without discussing them.""",
        )
        _accumulate(call_metrics)
        course_ids = _parse_course_ids(raw)

        feedback = environment.evaluate(course_ids)
        trial = ReflexionTrial(number=number, course_ids=course_ids, feedback=feedback)

        if feedback.score > best_score:
            best_course_ids, best_score = course_ids, feedback.score

        if feedback.success:
            trials.append(trial)
            metrics["status"] = "success"
            return ReflexionResult(True, course_ids, trials, memory[-memory_size:], metrics)

        reflection, call_metrics = _invoke(
            llm,
            system_prompt="You analyze why a proposed course path failed and state a specific strategy for the next attempt.",
            user_prompt=f"""Failed attempt: course_ids {course_ids}

Grounded environment feedback (score {feedback.score}):
{chr(10).join('- ' + item for item in feedback.details)}

State in one or two sentences, starting with 'I', what went wrong and the
specific strategy to use next trial (e.g. which course to drop or add).
Do not just repeat the feedback verbatim.""",
        )
        _accumulate(call_metrics)
        trial.reflection = reflection
        trials.append(trial)
        memory.append(reflection)

    metrics["status"] = "failed"
    return ReflexionResult(False, best_course_ids, trials, memory[-memory_size:], metrics)