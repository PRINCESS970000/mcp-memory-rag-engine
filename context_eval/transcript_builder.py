"""
Long-context test-case builder for context_eval/.

Real recurring need at Brightpeak Academy: academic-advising sessions.
An advisor bot pulls a student's live profile, course catalog, grade
updates, and reports across a long multi-turn session. Early in the call
a disciplinary flag can get mentioned once ("this student was expelled for
cheating, any future enrollment needs disciplinary-committee sign-off") and
then buried under dozens of routine tool calls (course listings, grade
look-ups, enrollment actions) before the advisor finally asks whether to
enroll that same student in a new course. If that flag doesn't survive,
the agent gives a materially wrong answer -- which is exactly the kind of
real cost the lab asks us to justify context management against.

Per the lab's cost note: input tokens are cheap, output tokens are
expensive/rate-limited. So the test suite leans hard on large, realistic
INPUT (repeated real tool-output payloads), not on generating huge model
output.
"""

import json
import random
from tool_samples import collect_samples

CRITICAL_DETAIL = (
    "IMPORTANT ADMIN NOTE: student Youssef Ibrahim (student_id=1) was "
    "expelled from the academy previously due to a documented cheating "
    "incident on the Database Systems exam. Any future re-admission or "
    "enrollment decision for him must first go through the disciplinary "
    "committee."
)

CRITICAL_KEYWORDS = ["cheating", "expelled", "disciplinary committee"]

FINAL_QUESTION = (
    "Student Youssef Ibrahim (student_id=1) wants to enroll in the "
    "Machine Learning course next term. Can we go ahead and enroll him "
    "directly, or is there something we need to check first?"
)

TOPICS = [
    "Show me the list of courses available this term.",
    "Pull up this student's profile and check their grades and enrolled courses.",
    "Enroll a new student in a course.",
    "Update a student's grade after regrading an exam.",
    "Give me a general academic report for the academy.",
    "Generate a detailed academic evaluation for this student.",
]


def _filler_turns(samples, n_groups, rng):
    """
    Ordinary advising-session chatter: user asks -> assistant calls a tool
    -> real (large) tool JSON comes back -> assistant summarizes briefly.
    Cycles through all 6 real tool outputs repeatedly, which is what
    actually inflates the transcript to thousands of tokens the way a real
    multi-hour advising session's tool traffic would.
    """
    tool_names = list(samples.keys())
    turns = []
    for i in range(n_groups):
        tool = tool_names[i % len(tool_names)]
        topic = TOPICS[i % len(TOPICS)]

        turns.append({"role": "user", "kind": "text",
                       "content": f"[Routine advising item #{i+1}] {topic}"})
        turns.append({"role": "assistant", "kind": "tool_call",
                       "content": f"Calling the `{tool}` tool to get the required data."})
        turns.append({"role": "tool", "kind": "tool_result",
                       "content": json.dumps(samples[tool], ensure_ascii=False)})
        turns.append({"role": "assistant", "kind": "text",
                       "content": f"`{tool}` executed successfully, result is shown above. "
                                  f"No further action needed right now for item #{i+1}."})
    return turns


def build_transcript(n_filler_groups=45, seed=0):
    """
    n_filler_groups=45 -> ~180 filler turns + tool JSON repeated many times
    -> realistically several thousand tokens of input, matching the lab's
    guidance to bury the decision under real tool-output bulk.
    """
    rng = random.Random(seed)
    samples = collect_samples()

    transcript = [{
        "role": "user", "kind": "text",
        "content": "Hi, let's start a long academic advising session today covering several students."
    }]

    transcript.append({"role": "user", "kind": "critical", "content": CRITICAL_DETAIL})
    transcript.append({
        "role": "assistant", "kind": "text",
        "content": "Noted. I'll make sure any future action involving student_id=1 "
                   "requires disciplinary-committee review before any new enrollment."
    })

    transcript += _filler_turns(samples, n_filler_groups, rng)
    transcript.append({"role": "user", "kind": "text", "content": FINAL_QUESTION})
    return transcript


def build_test_suite(n_copies=10, base_seed=100):
    """10 variations with different filler volume (35-55 groups), so token
    counts and cutoff points genuinely differ between runs."""
    suite = []
    for i in range(n_copies):
        n_groups = 35 + (i % 5) * 5  # 35, 40, 45, 50, 55 groups
        suite.append(build_transcript(n_filler_groups=n_groups, seed=base_seed + i))
    return suite


if __name__ == "__main__":
    t = build_transcript()
    total_chars = sum(len(x["content"]) for x in t)
    print(f"Transcript turns: {len(t)}")
    print(f"Approx. chars: {total_chars}  (~{total_chars // 4} tokens, rough estimate)")