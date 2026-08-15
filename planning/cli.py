from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

from .algorithms import (
    decompose_goal,
    dynamic_decomposition,
    execute_plan,
    final_output,
    flatten_lats_tree,
    lats,
    plan_and_solve,
    reflexion,
    Environment,
    tree_of_thoughts,
)


ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Week 4: decomposition, planning, and reflection lab")
    cli.add_argument("goal", nargs="?", default="Design a 60-minute phishing-awareness workshop for new employees")
    cli.add_argument(
        "--mode",
        choices=["dag", "dynamic", "ps", "tot", "reflexion", "lats"],
        default="dag",
    )
    cli.add_argument("--model", default="mistral-small-latest")
    cli.add_argument("--depth", type=int, default=2, choices=range(1, 4))
    cli.add_argument("--beam-width", type=int, default=2, choices=range(1, 4))
    cli.add_argument("--max-trials", type=int, default=3, choices=range(1, 6))
    cli.add_argument("--memory-size", type=int, default=3, choices=range(1, 6))
    cli.add_argument("--iterations", type=int, default=2, choices=range(1, 6))
    cli.add_argument("--n-actions", type=int, default=2, choices=range(1, 4))
    cli.add_argument(
        "--student-id",
        type=int,
        default=1,
        help="Real student_id in db/brightpeak.db; required for --mode reflexion/lats "
             "since Environment grounds every check against that student's real "
             "courses, prerequisites, and learning_goal (see mcp_server/server.py's "
             "get_path_planning_data).",
    )
    return cli


def save_artifact(payload: dict) -> Path:
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = artifact_dir / f"run-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    # Mistral may return arrows, em dashes, or other characters that Windows'
    # legacy cp1252 console cannot encode. UTF-8 keeps CLI output portable.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing; add it to .env")
    llm = ChatMistralAI(
        api_key=api_key,
        model=args.model,
        random_seed=42,
        max_retries=2,
    )
    payload: dict = {"mode": args.mode, "model": args.model, "goal": args.goal}

    if args.mode == "dag":
        plan = decompose_goal(args.goal, llm)
        print("Execution batches:", plan.execution_batches())
        outputs = execute_plan(plan, llm)
        result = final_output(plan, outputs)
        payload.update(plan=plan.model_dump(), outputs=outputs, result=result)
    elif args.mode == "dynamic":
        history = dynamic_decomposition(args.goal, llm)
        result = history[-1][1] if history else "Planner reported the goal was already complete."
        payload.update(history=history, result=result)
    elif args.mode == "ps":
        result, metrics = plan_and_solve(args.goal, llm)
        payload.update(result=result, metrics=metrics)
    elif args.mode == "tot":
        thoughts, metrics = tree_of_thoughts(args.goal, llm, args.depth, args.beam_width)
        result = thoughts[0].state if thoughts else "No viable thought survived."
        payload.update(
            thoughts=[thought.model_dump() for thought in thoughts],
            result=result,
            metrics=metrics,
        )
    elif args.mode == "reflexion":
        # Grounded: real student, real catalog/prerequisites/budget from
        # db/brightpeak.db via mcp_server's get_path_planning_data tool.
        mcp_server_path = str((ROOT / "mcp_server").resolve())
        environment = Environment(args.student_id, mcp_server_path=mcp_server_path)
        catalog_data = environment.get_catalog_data()
        outcome = reflexion(environment, catalog_data, llm, args.max_trials, args.memory_size)
        result = str(outcome.best_course_ids)
        payload.update(
            student_id=args.student_id,
            success=outcome.success,
            trials=[
                {
                    "number": trial.number,
                    "course_ids": trial.course_ids,
                    "feedback": trial.feedback.model_dump(),
                    "reflection": trial.reflection,
                }
                for trial in outcome.trials
            ],
            memory=outcome.memory,
            result=result,
            metrics=outcome.metrics,
        )
    else:
        mcp_server_path = str((ROOT / "mcp_server").resolve())
        environment = Environment(args.student_id, mcp_server_path=mcp_server_path)
        outcome, metrics = lats(args.goal, llm, environment, args.iterations, args.n_actions)
        result = outcome.output
        payload.update(
            student_id=args.student_id,
            success=outcome.success,
            best_score=outcome.best_score,
            iterations=outcome.iterations,
            tree=flatten_lats_tree(outcome.root),
            result=result,
            metrics=metrics,
        )

    artifact = save_artifact(payload)
    print("\nRESULT\n======\n" + result)
    print(f"\nRun artifact: {artifact}")


if __name__ == "__main__":
    main()