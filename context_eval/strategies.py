"""
Four context-management strategies, each with the same signature:

    compact(transcript: list[dict], budget_tokens: int) -> list[dict]

Each returns a NEW list of turns (still {"role","kind","content"} dicts)
representing what would actually be sent to the model, after being cut down
to roughly fit budget_tokens. We measure tokens with tiktoken separately in
the benchmark, so these functions work with a simple turn/word budget
internally and the benchmark re-measures real tokens on the output.
"""

import re
from transcript_builder import CRITICAL_KEYWORDS


def _contains_critical(text):
    return any(k in text for k in CRITICAL_KEYWORDS)


# ---------------------------------------------------------------------------
# 1. Sliding window
# ---------------------------------------------------------------------------
def sliding_window(transcript, window_turns=16):
    """
    Naive baseline: keep only the most recent `window_turns` turns, full
    stop. Nothing is protected -- if the critical detail falls outside the
    window, it's gone.
    """
    if len(transcript) <= window_turns:
        return list(transcript)
    return transcript[-window_turns:]


# ---------------------------------------------------------------------------
# 2. Observation masking
# ---------------------------------------------------------------------------
def observation_masking(transcript, keep_recent_tool_results=3):
    """
    Keeps ALL prose turns (user/assistant text, including the critical
    note) verbatim, but masks out old tool_result payloads beyond the most
    recent `keep_recent_tool_results`, replacing them with a short
    placeholder. This targets the actual token hog (large JSON tool
    outputs) without touching narrative content.
    """
    out = []
    tool_result_indices = [i for i, t in enumerate(transcript) if t["kind"] == "tool_result"]
    protected = set(tool_result_indices[-keep_recent_tool_results:]) if tool_result_indices else set()

    for i, turn in enumerate(transcript):
        if turn["kind"] == "tool_result" and i not in protected:
            out.append({
                "role": turn["role"], "kind": "tool_result",
                "content": "[older tool result omitted to save space]"
            })
        else:
            out.append(turn)
    return out


# ---------------------------------------------------------------------------
# 3. Recursive summarization
# ---------------------------------------------------------------------------
def _extractive_summarize(turns):
    """
    Stand-in for an LLM summarization call: a simple extractive summarizer
    that keeps sentences flagged as important (critical keywords, or
    status/error/result lines) and drops routine filler. This deliberately
    mimics a REAL risk of recursive summarization: if the summarizer's
    heuristic doesn't flag something as important, it gets compressed away
    -- exactly the failure mode we want the benchmark to be able to catch.
    """
    important_sentences = []
    for t in turns:
        text = t["content"]
        if t["kind"] == "critical" or _contains_critical(text):
            important_sentences.append(text)
    if not important_sentences:
        return "ملخص: عدد من عمليات الأدوات الروتينية (تسجيل، درجات، تقارير) بدون تفاصيل استثنائية."
    return "ملخص المحادثة السابقة: " + " | ".join(important_sentences)


def recursive_summarization(transcript, chunk_size=10, keep_recent_raw=8):
    """
    Splits the older part of the transcript into chunks and collapses each
    chunk into one summary turn via _extractive_summarize, then keeps the
    most recent `keep_recent_raw` turns untouched.
    """
    if len(transcript) <= keep_recent_raw:
        return list(transcript)

    older = transcript[:-keep_recent_raw]
    recent = transcript[-keep_recent_raw:]

    out = []
    for start in range(0, len(older), chunk_size):
        chunk = older[start:start + chunk_size]
        summary_text = _extractive_summarize(chunk)
        out.append({"role": "system", "kind": "summary", "content": summary_text})

    out.extend(recent)
    return out


# ---------------------------------------------------------------------------
# 4. Zone-based pruning
# ---------------------------------------------------------------------------
def zone_based_pruning(transcript, keep_recent_turns=10):
    """
    Splits the transcript into two explicit zones:
      - CRITICAL zone: any turn flagged kind=="critical" (or containing a
        critical keyword) -- always kept verbatim, no matter where it sits.
      - RECENT zone: the last `keep_recent_turns` turns -- kept verbatim.
      - Everything else (old, non-critical) is pruned to a one-line stub.
    This is the only strategy that explicitly protects the critical detail
    by content rather than relying on it surviving a recency/summary cutoff.
    """
    n = len(transcript)
    recent_start = max(n - keep_recent_turns, 0)

    out = []
    for i, turn in enumerate(transcript):
        is_critical = turn["kind"] == "critical" or _contains_critical(turn["content"])
        is_recent = i >= recent_start
        if is_critical or is_recent:
            out.append(turn)
        else:
            out.append({
                "role": turn["role"], "kind": "pruned",
                "content": "[pruned: routine turn, no critical content]"
            })
    return out


STRATEGIES = {
    "sliding_window": sliding_window,
    "observation_masking": observation_masking,
    "recursive_summarization": recursive_summarization,
    "zone_based_pruning": zone_based_pruning,
}