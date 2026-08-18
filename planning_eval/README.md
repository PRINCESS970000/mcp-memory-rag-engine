# planning_eval/

Fixed evaluation harness for the Adaptive Learning Path Planning agent.

## Contents

- `fixtures.py` — the 4 required real test cases (see rubric: decomposition-first
  favored, dynamic favored, lookahead-search needed, Reflexion-needed). **Frozen**
  once a run's traces get used in the comparison table — add new cases, don't edit
  existing ones.
- `run_decomposition_comparison.py` — decomposition-first vs. dynamic decomposition
  on `omar_stable_plan` and `kareem_dropped_course`. Saves
  `artifacts/decomposition_comparison_trace.json`.
- `run_lats_grounded_vs_ungrounded.py` — the same LATS task run against the real
  grounded `Environment` and against `random_environment_baseline.py`'s
  `RandomEnvironment` (the toolkit's original randomized default, kept only for
  this one comparison). Saves `artifacts/lats_grounded_vs_ungrounded_trace.json`.
- `run_reflexion_vs_selfrefine.py` — a single-pass Self-Refine-shaped baseline vs.
  the full Reflexion multi-trial loop on `salma_tight_constraints`, both using the
  same real grounded `Environment`. Saves `artifacts/self_refine_vs_reflexion_trace.json`.
- `run_self_refine_demo.py` — a standalone Self-Refine draft → critique → revision
  demo on its actual designed sub-task (the student-facing explanation). Saves
  `artifacts/self_refine_explanation_demo_trace.json`.
- `random_environment_baseline.py` — the intentionally-ungrounded `Environment`
  stand-in, used only by `run_lats_grounded_vs_ungrounded.py`.
- `demo_transcript.md` — full transcript compiling all four comparisons above.

The comparison table built from these traces is embedded directly in the
repo root `README.md` (not duplicated here) — see the "Summary of Execution
Traces & Performance Metrics" section there.

## Still needed

- `build_table.py` — a script that reads every trace in `artifacts/` and
  regenerates the comparison table automatically. Not blocking: the table
  itself already exists, hand-compiled from these same traces, in the root
  `README.md`. This would make it reproducible without manual copying.

## Running

All scripts need a real `MISTRAL_API_KEY` in a `.env` file at the repo root
(not `ANTHROPIC_API_KEY` — the whole `planning/` package standardized on
`ChatMistralAI` so one key covers every algorithm):

```bash
cd mcp-memory-rag-engine
python -m planning_eval.run_decomposition_comparison
python -m planning_eval.run_lats_grounded_vs_ungrounded
python -m planning_eval.run_reflexion_vs_selfrefine
python -m planning_eval.run_self_refine_demo
```

Each run appends/overwrites its own trace file in `artifacts/` and prints a
summary to stdout.