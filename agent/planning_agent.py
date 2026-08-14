from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

from planning.algorithms import (
    decompose_goal,
    dynamic_decomposition,
    execute_plan,
    final_output,
)
from planning.algorithms.environment import Environment
from planning.algorithms.self_refine import refine_synthesis_output

ROOT = Path(__file__).resolve().parents[1]


def save_artifact(payload: dict) -> Path:
    """Same shape/location as the toolkit's cli.py save_artifact -- one
    JSON trace per run in artifacts/, reused rather than duplicated."""
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = artifact_dir / f"planning-agent-run-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_learning_path_request(student_id: int, goal: str, llm, mode: str = "dag") -> dict:
    """Main entry point: request in, trace + result out. `mode` picks
    decomposition-first ("dag") or interleaved ("dynamic") -- both are
    required to run against the same real request type per the rubric.

    `student_id` is required (not inferred from `goal`'s text) because
    Environment.evaluate() checks this specific student's real budget,
    weekly hours, completed courses, and deadline -- there is no safe
    default student to fall back to."""
    payload: dict = {"mode": mode, "goal": goal, "student_id": student_id}
    environment = Environment(student_id=student_id, mcp_server_path=str(ROOT / "mcp_server"))

    if mode == "dag":
        plan = decompose_goal(goal, llm)
        outputs, metrics_by_task = execute_plan(plan, llm, environment=environment)
        raw_result = final_output(plan, outputs)

        # Self-Refine pass on the synthesis task's output specifically --
        # not on the whole plan -- since that's the sub-task type this
        # algorithm is routed to (see self_refine.py's module docstring).
        refinement = refine_synthesis_output(goal, raw_result, environment, llm)
        result = refinement.revised

        payload.update(
            plan=plan.model_dump(),
            execution_batches=plan.execution_batches(),
            outputs=outputs,
            metrics_by_task=metrics_by_task,
            raw_synthesis_output=raw_result,
            self_refine_grounded_issues=refinement.grounded_issues,
            self_refine_critique=refinement.critique,
            result=result,
        )
    elif mode == "dynamic":
        history = dynamic_decomposition(goal, llm)
        result = history[-1][1] if history else "Planner reported the goal was already complete."
        payload.update(history=history, result=result)
    else:
        raise ValueError(f"Unknown mode: {mode!r} (expected 'dag' or 'dynamic')")

    artifact_path = save_artifact(payload)
    payload["artifact_path"] = str(artifact_path)
    return payload


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BrightPeak Learning Path Planning agent")
    parser.add_argument("student_id", type=int, help="The real student_id this plan is for")
    parser.add_argument("goal", help="The student's learning-path request, in plain text")
    parser.add_argument("--mode", choices=["dag", "dynamic"], default="dag")
    parser.add_argument("--model", default="mistral-small-latest")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = _cli().parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env")

    llm = ChatMistralAI(api_key=api_key, model=args.model, random_seed=42, max_retries=2)

    payload = run_learning_path_request(args.student_id, args.goal, llm, mode=args.mode)

    print("\nRESULT\n======\n" + payload["result"])
    print(f"\nRun artifact: {payload['artifact_path']}")


if __name__ == "__main__":
    main()