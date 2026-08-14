"""
Self-Refine for the Adaptive Learning Path Planning agent.

Sub-task this is routed to: generating the human-readable explanation the
student sees, justifying the recommended path (which courses, why, total
cost, timeline). This is cheap to redo -- a single short paragraph -- which
is exactly the kind of output Self-Refine fits (one draft, one critique
against an explicit rubric, one revision). It is NOT used for the path
search itself (that's LATS's job) or for full re-attempts across trials
(that's Reflexion's job, in reflexion.py).

Adapted from the toolkit's algorithms/self_refine.py:
- Same overall shape: grounded_path_checks() feed a grounded_report into
  the critique prompt, then a revision step.
- LLM client: uses `llm: BaseChatModel` and `llm.invoke([...])`, the same
  convention plan_and_solve.py / tree_of_thoughts.py / lats.py already use
  (ChatMistralAI in practice, see agent/planning_agent.py), instead of
  calling the Anthropic SDK directly -- keeps one consistent LLM provider
  across the whole planning/ package rather than requiring two API keys
  for one agent run.

Grounded vs. ungrounded, explicitly:
- UNGROUNDED: the critique_response call below asks the model to judge its
  own draft against a rubric. It can catch vague or incomplete writing, but
  it cannot catch a *factual* error confidently stated in fluent prose --
  a wrong total price or a course that isn't actually in the path reads
  just as "correct-sounding" to the same model that wrote it.
- GROUNDED: grounded_path_checks() below never calls an LLM. It checks the
  draft's claims against the same real data environment.py validates paths
  against (course titles, prices) -- deterministic string/number matching,
  not opinion.
See planning_eval/ for the documented case where grounded_path_checks()
caught a wrong total-cost claim that the ungrounded critique alone missed.
"""

import re
import time
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel


def grounded_path_checks(draft: str, path_courses: list[dict], all_courses: list[dict], total_price: float) -> list[str]:
    """Check the draft's factual claims against real course data -- the
    same `courses` records environment.py's evaluate() checks the path
    against. No LLM call, no opinion, just string/number matching."""
    issues: list[str] = []
    draft_lower = draft.lower()

    for course in path_courses:
        if course["title"].lower() not in draft_lower:
            issues.append(
                f"Draft doesn't mention '{course['title']}' (course_id "
                f"{course['course_id']}), which is part of the recommended path."
            )

    path_ids = {c["course_id"] for c in path_courses}
    for course in all_courses:
        if course["course_id"] not in path_ids and course["title"].lower() in draft_lower:
            issues.append(
                f"Draft mentions '{course['title']}', which is NOT part of "
                f"the recommended path -- likely a hallucinated course."
            )

    mentioned_numbers = [float(n) for n in re.findall(r"\d+(?:\.\d{1,2})?", draft)]
    if not any(abs(n - total_price) < 1.0 for n in mentioned_numbers):
        issues.append(
            f"Draft doesn't state the correct total cost (${total_price:.2f}); "
            f"numbers mentioned: {mentioned_numbers or 'none'}."
        )

    return issues


# Backward-compatible alias: the shared planning/algorithms/__init__.py
# also exports the name `deterministic_checks` from the original toolkit.
deterministic_checks = grounded_path_checks


@dataclass
class ReflectionResult:
    draft: str
    critique: str
    revised: str
    grounded_issues: list[str]
    metrics: dict


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
        raise RuntimeError("Self-Refine: the chat model returned an empty or unsupported response.")

    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
        usage = response.response_metadata["token_usage"]
        token_usage["prompt_tokens"] = usage.get("prompt_tokens", 0)
        token_usage["completion_tokens"] = usage.get("completion_tokens", 0)
        token_usage["total_tokens"] = usage.get(
            "total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        )

    return response.content.strip(), {"latency_seconds": latency, **token_usage}


def reflect_and_refine(
    goal: str,
    draft: str,
    path_courses: list[dict],
    all_courses: list[dict],
    total_price: float,
    llm: BaseChatModel,
) -> ReflectionResult:
    grounded = grounded_path_checks(draft, path_courses, all_courses, total_price)
    grounded_report = "\n".join(f"- {issue}" for issue in grounded) or "- Grounded checks passed."

    metrics = {"algorithm": "Self-Refine", "llm_calls": 0, "prompt_tokens": 0,
               "completion_tokens": 0, "total_tokens": 0, "latency_seconds": 0.0}

    # UNGROUNDED step: a separate call, same model, judging the draft's
    # writing quality against a rubric -- it does not re-verify the facts.
    critique, call_metrics = _invoke(
        llm,
        system_prompt=(
            "You are a separate critic reviewing a student-facing explanation. "
            "Judge it against the rubric: clarity, encouraging tone, and whether "
            "it mentions the timeline. Do not rewrite it."
        ),
        user_prompt=f"""Goal: {goal}

External grounded checks (already run, treat as ground truth):
{grounded_report}

Draft:
{draft}

List concrete writing-quality issues. If there are none, respond exactly PASS.""",
    )
    metrics["llm_calls"] += 1
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        metrics[k] += call_metrics[k]
    metrics["latency_seconds"] += call_metrics["latency_seconds"]

    if critique.upper() == "PASS" and not grounded:
        revised = draft
    else:
        revised, call_metrics = _invoke(
            llm,
            system_prompt=(
                "You revise a student-facing explanation using grounded checks and "
                "a critique. The grounded checks are facts you must fix exactly as "
                "stated -- don't second-guess them."
            ),
            user_prompt=f"""Goal: {goal}

Draft:
{draft}

Grounded checks:
{grounded_report}

Critique:
{critique}

Return only the improved explanation.""",
        )
        metrics["llm_calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            metrics[k] += call_metrics[k]
        metrics["latency_seconds"] += call_metrics["latency_seconds"]
        metrics["latency_seconds"] = round(metrics["latency_seconds"], 3)

    metrics["status"] = "success"
    return ReflectionResult(draft, critique, revised, grounded, metrics)


def refine_synthesis_output(goal: str, draft: str, environment, llm: BaseChatModel) -> ReflectionResult:
    """Entry point for decomposition.py's synthesis task: the DAG's final
    task (category="deterministic_parsing", the one that writes the
    student-facing summary) produces `draft` as plain text with no
    guaranteed structure. This wraps reflect_and_refine() so the caller
    doesn't have to build path_courses/all_courses/total_price by hand --
    it pulls them from the same Environment instance execute_plan() is
    already using for this student, via the course_ids the draft mentions.

    Import is deferred (function-local) to avoid a circular import:
    environment.py doesn't import self_refine.py, but this keeps the
    dependency one-directional regardless of import order elsewhere in
    the package."""
    from .environment import Environment  # local import: see docstring above

    data = environment.get_catalog_data()
    all_courses = data["courses"]
    courses_by_id = {c["course_id"]: c for c in all_courses}

    course_ids = Environment._extract_course_ids(
        environment, draft, valid_ids=set(courses_by_id)
    )
    path_courses = [courses_by_id[cid] for cid in course_ids if cid in courses_by_id]
    total_price = sum(c["price"] for c in path_courses)

    return reflect_and_refine(goal, draft, path_courses, all_courses, total_price, llm)