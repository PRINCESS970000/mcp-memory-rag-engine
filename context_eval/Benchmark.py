"""
Runs all 4 context-management strategies against a 10-copy long-context
test suite, then for each run: compacts the transcript (that's the INPUT
tokens the model would actually be billed for), generates the agent's
final answer from that compacted context (the OUTPUT tokens), and scores
whether the answer was actually correct (task accuracy) -- not just
whether the raw fact string survived somewhere in the context.

Produces the comparison table required by the rubric:
  accuracy | avg input tokens/run | avg output tokens/run | avg latency
"""

import time
import re
import statistics as stats

from transcript_builder import build_test_suite
from strategies import STRATEGIES
from generate_step import generate_answer

# Same fallback tokenizer as before -- tiktoken needs network access to its
# BPE vocab file, which is blocked in this sandbox. Applied identically to
# every strategy's input and output, so the comparison stays fair.
_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text_or_turns):
    if isinstance(text_or_turns, str):
        text = text_or_turns
    else:
        text = "\n".join(t["content"] for t in text_or_turns)
    return len(_TOKEN_RE.findall(text))


def run_benchmark(n_copies=10):
    suite = build_test_suite(n_copies=n_copies)
    results = {name: [] for name in STRATEGIES}

    for run_idx, transcript in enumerate(suite):
        for name, fn in STRATEGIES.items():
            start = time.perf_counter()
            compacted = fn(transcript)                    # context-mgmt step
            answer, correct = generate_answer(compacted)   # generation step
            elapsed_s = time.perf_counter() - start

            input_tokens = count_tokens(compacted)
            output_tokens = count_tokens(answer)

            results[name].append({
                "run": run_idx,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_s": elapsed_s,
                "correct": correct,
            })

    return results


def summarize(results):
    rows = []
    for name, runs in results.items():
        accuracy = sum(r["correct"] for r in runs) / len(runs)
        avg_in = stats.mean(r["input_tokens"] for r in runs)
        avg_out = stats.mean(r["output_tokens"] for r in runs)
        avg_latency = stats.mean(r["latency_s"] for r in runs)
        n_correct = sum(r["correct"] for r in runs)
        rows.append({
            "strategy": name,
            "accuracy": f"{n_correct}/{len(runs)}",
            "avg_input_tokens": round(avg_in, 0),
            "avg_output_tokens": round(avg_out, 0),
            "avg_latency_s": round(avg_latency, 4),
        })
    return rows


def print_table(rows):
    headers = ["strategy", "accuracy", "avg_input_tokens", "avg_output_tokens", "avg_latency_s"]
    widths = {h: max(len(h), max(len(str(r[h])) for r in rows)) for h in headers}

    def fmt(vals):
        return " | ".join(str(v).ljust(widths[h]) for h, v in zip(headers, vals))

    print(fmt(headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for r in rows:
        print(fmt([r[h] for h in headers]))


def to_markdown_table(rows):
    headers = ["Strategy", "Accuracy (10 runs)", "Avg. input tokens/run",
               "Avg. output tokens/run", "Avg. latency"]
    keys = ["strategy", "accuracy", "avg_input_tokens", "avg_output_tokens", "avg_latency_s"]
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        vals = [str(r[k]) for k in keys]
        vals[-1] = f"{vals[-1]}s"
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def pick_winner(rows):
    """Must be 100% accurate to qualify -- a wrong disciplinary answer is
    disqualifying regardless of cost. Among qualifiers, lowest avg input
    tokens wins (input is the cheap-but-real cost driver here); ties
    broken by avg output tokens, then latency."""
    perfect = [r for r in rows if r["accuracy"].split("/")[0] == r["accuracy"].split("/")[1]]
    if not perfect:
        return None
    return sorted(perfect, key=lambda r: (r["avg_input_tokens"], r["avg_output_tokens"], r["avg_latency_s"]))[0]


if __name__ == "__main__":
    results = run_benchmark(n_copies=10)
    rows = summarize(results)

    print("\n================ Comparison Table (10-run long-context suite) ================\n")
    print_table(rows)

    winner = pick_winner(rows)
    print("\n================ Decision ================\n")
    if winner:
        print(f"Winner: {winner['strategy']}")
        print(f"  accuracy          = {winner['accuracy']}")
        print(f"  avg_input_tokens  = {winner['avg_input_tokens']}")
        print(f"  avg_output_tokens = {winner['avg_output_tokens']}")
        print(f"  avg_latency_s     = {winner['avg_latency_s']}")
    else:
        print("No strategy reached 100% task accuracy.")

    print("\n================ Markdown table for README ================\n")
    print(to_markdown_table(rows))