\# planning\_eval/



Fixed evaluation harness for the Adaptive Learning Path Planning agent.



\## Contents

\- `fixtures.py` — the 4 required real test cases (see rubric: decomposition-first

&nbsp; favored, dynamic favored, lookahead-search needed, Reflexion-needed). \*\*Frozen\*\*

&nbsp; once a run's traces get used in the comparison table — add new cases, don't edit

&nbsp; existing ones.

\- `run\_reflexion\_vs\_selfrefine.py` — runs a single-pass Self-Refine-shaped baseline

&nbsp; vs. the full Reflexion multi-trial loop on `salma\_tight\_constraints`, both using

&nbsp; the same real grounded `Environment`. Saves `artifacts/self\_refine\_vs\_reflexion\_trace.json`.

\- `artifacts/` — JSON traces backing the comparison table (same format the toolkit's

&nbsp; own `cli.py` already uses — not a second logging system).



\## Still needed (owners in parentheses)

\- `run\_decomposition\_comparison.py` (Person 1) — `omar\_stable\_plan` vs

&nbsp; `kareem\_dropped\_course`, decomposition-first vs dynamic.

\- `run\_planning\_comparison.py` (Person 2) — PS vs ToT vs LATS on

&nbsp; `hoda\_many\_valid\_orderings`; LATS grounded (`Environment`) vs ungrounded

&nbsp; (`RandomEnvironment` baseline) needs Person 2's `lats()` wired to the team's

&nbsp; actual LLM client before it can run for real.

\- `build\_table.py` — reads every trace in `artifacts/` and produces the one

&nbsp; comparison table required by the rubric (accuracy, LLM calls, tokens, latency,

&nbsp; cost per method).



\## Running

```bash

cd mcp-memory-rag-engine

python -m planning\_eval.run\_reflexion\_vs\_selfrefine

```

Requires `ANTHROPIC\_API\_KEY` in `.env` at the repo root for real (non-mocked) runs.

