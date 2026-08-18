\# Demo Transcript — Adaptive Learning Path Planning Agent



All outputs below are real runs against BrightPeak Academy's actual `db/`

via `mcp\_server/get\_path\_planning\_data`, using `ChatMistralAI` (Mistral).

No numbers are invented or estimated. Full JSON traces are in

`planning\_eval/artifacts/`.



---



\## 1. Decomposition-first vs. dynamic decomposition — the divergence



\*\*Student:\*\* Kareem Reda (student\_id=7), target role Software Engineer.

\*\*Real data fact used:\*\* his `enrollments` row shows `course\_id=1

("Introduction to Computer Science")`, `grade=45.0`, `status=DROPPED`.



\*\*Decomposition-first\*\* (whole plan generated in one shot, 3.55s):

generates a generic 8-task plan — `get\_student\_profile` →

`get\_role\_requirements` → `search\_courses` → gap analysis → rank →

`check\_prerequisites` → `enroll\_student` → synthesize. None of these

tasks specifically references the dropped course; the plan would execute

identically whether Kareem had passed, failed, or never taken course 1.



\*\*Dynamic decomposition\*\* (next step generated after observing the last,

7.09s): step 1 retrieves Kareem's profile and observes the real

`DROPPED` / `grade: 45.0` status. By step 4, `search\_courses` surfaces

`course\_id=1` again as a live candidate — the plan is reacting to the

real failure decomposition-first would have silently ignored, without

being told to "handle a dropped course" anywhere in the prompt.



Full trace: `planning\_eval/artifacts/decomposition\_comparison\_trace.json`



---



\## 2. LATS grounded vs. ungrounded `Environment`



\*\*Student:\*\* Hoda Mansour (student\_id=6), target role ML Engineer, the

least-constrained student in the seed data (budget $1000, 15 hrs/week) —

meaning many plausible-sounding paths exist for an ungrounded evaluator

to score well by chance.



\*\*Ungrounded LATS\*\* (`RandomEnvironment`, the toolkit's original

randomized default), 1 iteration, 2 LLM calls, 3.4s:

\- Proposed a 6-course path, reported \*\*`success: true`, score 0.84\*\*

\- Real grounded check of that \*exact same output\*: \*\*`success: false`,

&nbsp; score 0.5\*\* — the path actually costs $1930 (budget is $1000, a 93%

&nbsp; overrun), several courses overlap at up to 38 hrs/week (limit: 15),

&nbsp; and course 3 starts before its own prerequisite (course 1) ends.



\*\*Grounded LATS\*\* (real `Environment`, real MCP/DB checks), 2 iterations,

10 LLM calls, 26.7s:

\- Reported \*\*`success: false`, score 0.83\*\* — costs more calls and never

&nbsp; falsely claims success on this genuinely tight catalog, which is the

&nbsp; correct behavior.



This is the case the grounding requirement exists for: the ungrounded run

was 8x cheaper and \*believed\* it had succeeded, but its own proposal

would have double-booked the student's schedule and blown the budget by

93%. LATS ships wired to the real `Environment` for exactly this reason.



Full trace: `planning\_eval/artifacts/lats\_grounded\_vs\_ungrounded\_trace.json`



---



\## 3. Reflexion — reflection carried across trials



\*\*Student:\*\* Salma Farouk (student\_id=8), the tightest simultaneous

constraints in the seed data (budget $500, 8 hrs/week, deadline

2026-12-01).



3 real trials, 6 LLM calls total, converging from score 0.17 (Self-Refine

baseline, below) to \*\*0.50\*\*:



> \*\*Trial 1 reflection:\*\* "I overloaded the schedule with too many

> high-overlap courses and ignored prerequisite sequencing and budget

> constraints; next, I'll prioritize non-overlapping courses, space them

> out, and ensure prerequisites are completed before dependent courses

> start, while strictly adhering to the 500-hour budget."



> \*\*Trial 2 reflection:\*\* "I overloaded my schedule by enrolling in too

> many high-overlap courses too soon, violating time, budget, and

> prerequisite constraints. Next, I'll prioritize courses sequentially,

> starting with prerequisites, and ensure no weekly hour total exceeds 8

> while staying under the $500 budget."



> \*\*Trial 3 reflection:\*\* "I failed because I didn't properly sequence

> prerequisite courses and packed too many high-hour courses

> simultaneously... Next, I'll prioritize prerequisites first (e.g.,

> complete course 1 before 14, 3, or 4), space out high-hour courses...

> starting with course 1 alone, then carefully adding others."



Each reflection is visibly more specific than the last (generic →

sequencing-aware → course-ID-specific), confirming the memory buffer is

genuinely read and built on, not reset each trial.



Full trace: `planning\_eval/artifacts/self\_refine\_vs\_reflexion\_trace.json`



---



\## 4. Self-Refine — grounded critique catching a real arithmetic error



\*\*Student:\*\* Omar Khaled (student\_id=1), sub-task: writing the

student-facing explanation (Self-Refine's actual designed sub-task, not

the path proposal itself).



\*\*Draft (deliberately seeded with a plausible LLM arithmetic slip):\*\*

> "To become a Data Scientist, I recommend starting with Statistics for

> Data Science and Business Communication for Tech Teams. Together these

> cost about \*\*$390.00\*\* and will build your foundational skills."



\*\*Grounded check\*\* (`grounded\_path\_checks`, no LLM call): real sum of the

two courses' prices is \*\*$240.00\*\*, not $390 — flagged immediately.



\*\*Revision:\*\*

> "To become a Data Scientist, I recommend starting with \*\*Statistics for

> Data Science\*\*, which costs $120, and \*\*Business Communication for Tech

> Teams\*\*, which costs $120. Together, these courses total \*\*$240.00\*\*

> and will build your foundational skills in data analysis and

> professional communication."



2 LLM calls, 619 tokens, 2.96s. The revision doesn't just soften the

language — it corrects the actual number using the grounded check's real

figure, not a re-guess.



Full trace: `planning\_eval/artifacts/self\_refine\_explanation\_demo\_trace.json`

