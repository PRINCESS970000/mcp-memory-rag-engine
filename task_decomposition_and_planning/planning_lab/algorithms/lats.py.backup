from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Tuple, Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from ..models import EnvironmentFeedback
from .environment import Environment


class LATSAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=2)
    course_ids: list[int] = Field(min_length=1)
    state: str = Field(min_length=2)


class LATSActionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[LATSAction] = Field(min_length=1, max_length=3)


class ValueEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)


def _extract_token_usage(raw_message) -> Tuple[int, int]:
    """Same fix as tree_of_thoughts.py: with_structured_output(...).invoke()
    returns only the parsed pydantic object (no response_metadata) unless
    include_raw=True is passed, which returns {"raw": AIMessage, "parsed": ...}.
    Without this, token counts silently stayed at 0 for every LATS call."""
    if raw_message is None:
        return 0, 0
    metadata = getattr(raw_message, "response_metadata", None) or {}
    usage = metadata.get("token_usage", {})
    return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


@dataclass
class LATSNode:
    state: str
    action: str = "root"
    parent: LATSNode | None = field(default=None, repr=False)
    children: list[LATSNode] = field(default_factory=list, repr=False)
    visits: int = 0
    value_sum: float = 0.0
    environment_score: float = 0.0
    model_score: float = 0.0
    feedback: EnvironmentFeedback | None = None
    reflections: list[str] = field(default_factory=list)

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass
class LATSResult:
    success: bool
    output: str
    best_score: float
    iterations: int
    root: LATSNode


def _uct(node: LATSNode, exploration_weight: float) -> float:
    if node.visits == 0:
        return float("inf")
    parent_visits = max(node.parent.visits if node.parent else 1, 1)
    return node.mean_value + exploration_weight * math.sqrt(math.log(parent_visits) / node.visits)


def _select_leaf(root: LATSNode, exploration_weight: float) -> LATSNode:
    node = root
    while node.children:
        node = max(node.children, key=lambda child: _uct(child, exploration_weight))
    return node


def _backpropagate(node: LATSNode, value: float) -> None:
    while node is not None:
        node.visits += 1
        node.value_sum += value
        node = node.parent


def _trajectory_reflections(node: LATSNode) -> list[str]:
    path: list[str] = []
    while node is not None:
        path.extend(node.reflections)
        node = node.parent
    return list(reversed(path))


def lats(
    task: str,
    llm: BaseChatModel,
    environment: Environment,
    iterations: int = 2,
    n_actions: int = 2,
    exploration_weight: float = 1.414,
    task_type: str = "schedule_optimization_and_validation"
) -> Tuple[LATSResult, Dict[str, Any]]:
    """
    Language Agent Tree Search (LATS) implementation for final high-cost schedule optimization.
    
    Targeted sub-tasks:
    - Final schedule optimization where wrong plans cost time/money (e.g., schedule conflict or budget overflow).
    - Uses MCTS (Select, Expand/Simulate, Evaluate via Grounded Environment, Backpropagate).
    - Integrates external EnvironmentFeedback provided by Person 3's validator.
    """
    start_time = time.time()

    planning_data = environment.get_catalog_data()

    courses_by_id = {
        c["course_id"]: c
        for c in planning_data["courses"]
    }

    goal_data = planning_data["learning_goal"]

    catalog_text = "\n".join(
        f"Course {c['course_id']}: {c['title']} | "
        f"price=${c['price']} | "
        f"weekly_hours={c['weekly_hours']} | "
        f"dates={c['start_date']} to {c['end_date']} | "
        f"difficulty={c['difficulty']} | "
        f"skills={c['skill_tags']}"
        for c in planning_data["courses"]
    )

    constraints_text = f"""
Target role required skills:
{", ".join(planning_data["required_skills"])}

Budget: ${goal_data["budget"]}
Weekly hours available: {goal_data["weekly_hours_available"]}
Target date: {goal_data["target_date"]}
Completed courses: {planning_data["completed_course_ids"]}

Prerequisites:
{planning_data["prerequisites"]}
"""
    if iterations < 1 or n_actions < 1:
        raise ValueError("iterations and n_actions must be positive")
        
    total_llm_calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    root = LATSNode(state="No attempt yet.")
    best = root
    completed_iterations = 0

    for iteration in range(1, iterations + 1):
        completed_iterations = iteration
        
        # 1. Selection Phase
        leaf = _select_leaf(root, exploration_weight)
        lessons = _trajectory_reflections(leaf)
        lesson_text = "\n".join(f"- {item}" for item in lessons[-4:]) or "- None yet."

        # 2. Expansion / Simulation Phase
        action_prompt = [
            (
                "system",
                """You are the action generator in LATS for Adaptive Learning Path Planning.

IMPORTANT RULES:
1. You MUST use ONLY courses from the provided BrightPeak course catalog.
2. You MUST NOT invent courses, providers, platforms, prices, durations, skills, roles, or deadlines.
3. Every candidate MUST use course IDs from the catalog.
4. Respect prerequisites, budget, weekly-hour limit, required skills, and deadline.
5. The student's completed courses are already satisfied.
6. Prefer a valid feasible path over an impressive but invented path."""
            ),
            (
                "human",
                f"""Task:
{task}

REAL STUDENT CONSTRAINTS:
{constraints_text}

REAL BRIGHTPEAK COURSE CATALOG:
{catalog_text}

Current trajectory/state:
{leaf.state}

Reflections learned from failed branches:
{lesson_text}

Propose exactly {n_actions} distinct candidate learning paths.

For EACH candidate:
- provide course_ids in the intended order
- use ONLY course IDs from the catalog
- provide a complete human-readable state
- include total cost
- include weekly hours
- make sure prerequisites are satisfied
- cover the required skills
- finish by the target date

Do NOT invent any course."""
            ),
        ]

        proposed_result = llm.with_structured_output(
            LATSActionBatch,
            method="json_schema",
            include_raw=True,
        ).invoke(action_prompt, temperature=0.5)
        proposed = proposed_result["parsed"]

        total_llm_calls += 1

        prompt_tok, completion_tok = _extract_token_usage(proposed_result["raw"])
        total_prompt_tokens += prompt_tok
        total_completion_tokens += completion_tok

        for item in proposed.actions[:n_actions]:
            child_state = item.state.strip()

            child = LATSNode(
                state=child_state,
                action=item.action,
                 parent=leaf,
            )
            leaf.children.append(child)

            # 3. Evaluation Phase (Grounded Feedback from Person 3's Environment)
            feedback = environment.evaluate(item.course_ids)
            child.feedback = feedback
            child.environment_score = feedback.score

            # LLM Value Estimate
            value_prompt = [
                ("system", "You are the LATS value function estimating learning path quality."),
                ("human", f"""Task: {task}

Candidate course IDs:
{item.course_ids}

Candidate state:
{child.state}
External score: {feedback.score}
External feedback: {feedback.details}
Estimate the candidate's future usefulness for the student's career goal."""),
            ]

            value_result = llm.with_structured_output(
                ValueEstimate,
                method="json_schema",
                include_raw=True,
            ).invoke(value_prompt, temperature=0.1)
            value_judgment = value_result["parsed"]

            total_llm_calls += 1

            prompt_tok, completion_tok = _extract_token_usage(value_result["raw"])
            total_prompt_tokens += prompt_tok
            total_completion_tokens += completion_tok

            child.model_score = value_judgment.score
            
            # Combine Grounded Environment Score (75%) and LLM Value Judgment (25%)
            combined_value = 0.75 * child.environment_score + 0.25 * child.model_score

            # Reflection Generation if Grounded Environment failed
            if not feedback.success:
                reflect_prompt = [
                    ("system", "Create a branch-level LATS reflection grounded in environment feedback."),
                    ("human", f"""Task: {task}
Action: {child.action}
Course IDs: {item.course_ids}
Resulting state: {child.state}
External feedback: {feedback.details}
Explain briefly why this proposed learning path failed and how a later expansion should change."""),
                ]
                
                response = llm.invoke(reflect_prompt, temperature=0.2)
                total_llm_calls += 1

                if hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
                    usage = response.response_metadata["token_usage"]
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)

                reflection = response.content
                if not isinstance(reflection, str) or not reflection.strip():
                    raise RuntimeError("LATS: The chat model returned an empty or unsupported response")
                
                reflection = reflection.strip()
                child.reflections.append(reflection)

            # 4. Backpropagation Phase
            _backpropagate(child, combined_value)

            if best is root or child.environment_score > best.environment_score:
                best = child

            if feedback.success:
                latency = round(time.time() - start_time, 3)
                metrics = {
                    "algorithm": "LATS",
                    "task_type": task_type,
                    "llm_calls": total_llm_calls,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                    "latency_seconds": latency,
                    "iterations_used": completed_iterations,
                    "best_score": child.environment_score,
                    "status": "success"
                }
                return LATSResult(True, child.state, child.environment_score, completed_iterations, root), metrics

    latency = round(time.time() - start_time, 3)
    metrics = {
        "algorithm": "LATS",
        "task_type": task_type,
        "llm_calls": total_llm_calls,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "latency_seconds": latency,
        "iterations_used": completed_iterations,
        "best_score": best.environment_score,
        "status": "failed"
    }
    return LATSResult(False, best.state, best.environment_score, completed_iterations, root), metrics


def flatten_lats_tree(root: LATSNode) -> list[dict]:
    records: list[dict] = []
    queue: list[tuple[LATSNode, str | None]] = [(root, None)]
    next_id = 0
    while queue:
        node, parent_id = queue.pop(0)
        node_id = f"n{next_id}"
        next_id += 1
        records.append(
            {
                "id": node_id,
                "parent_id": parent_id,
                "action": node.action,
                "state": node.state,
                "visits": node.visits,
                "mean_value": node.mean_value,
                "environment_score": node.environment_score,
                "model_score": node.model_score,
                "feedback": node.feedback.model_dump() if node.feedback else None,
                "reflections": node.reflections,
            }
        )
        queue.extend((child, node_id) for child in node.children)
    return records