"""
Runs all 3 retrieval architectures (naive, hybrid, agentic) against the 12
test questions in test_questions.py, and produces a comparison table.

Retrieval accuracy is scored as a HIT if every id in a question's
expected_chunk_ids appears somewhere in that architecture's returned
results -- this measures whether retrieval found the right material,
independent of whether the generated answer is phrased correctly.

By default this only measures retrieval (fast, free, no API calls).
Pass --generate to also call generate.py's generate_answer() for each hit
and report real input/output token usage and end-to-end latency. This
costs API credits, so it's opt-in.

Usage (run from inside rag/):
    python ../retrieval_eval/run_comparison.py
    python ../retrieval_eval/run_comparison.py --generate
"""

import argparse
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

from ingest import load_all_policies
from vector_store import get_client, get_or_create_collection
from naive_rag import naive_rag_search
from hybrid_rag import build_bm25_index, hybrid_search
from agentic_rag import agentic_rag_search

sys.path.insert(0, str(Path(__file__).parent))
from test_questions import TEST_QUESTIONS


def is_hit(expected_ids, returned_chunks):
    returned_ids = {c.chunk_id for c, _score in returned_chunks}
    return all(eid in returned_ids for eid in expected_ids)


def run_naive(collection, question, n_results=3):
    start = time.perf_counter()
    results = naive_rag_search(collection, question, n_results=n_results)
    elapsed = time.perf_counter() - start
    return results, elapsed


def run_hybrid(collection, bm25_index, chunks, question, n_results=3):
    start = time.perf_counter()
    results = hybrid_search(collection, bm25_index, chunks, question, n_results=n_results)
    elapsed = time.perf_counter() - start
    return results, elapsed


def run_agentic(collection, bm25_index, chunks, question, n_results=3):
    start = time.perf_counter()
    results, reasoning_log = agentic_rag_search(collection, bm25_index, chunks, question, n_results=n_results)
    elapsed = time.perf_counter() - start
    return results, elapsed, reasoning_log


def maybe_generate(question, results, do_generate):
    """Returns (answer_text_or_None, input_tokens, output_tokens)."""
    if not do_generate:
        return None, 0, 0
    from generate import client, MODEL
    chunks_only = [c for c, _score in results]
    context = "\n\n".join(
        f"[{c.document_id} — Section {c.section_id}: {c.section_title}]\n{c.text}"
        for c in chunks_only
    )
    prompt = f"""You are answering a question using ONLY the policy excerpts below.
If the excerpts do not contain enough information to answer, say so explicitly --
do not use any outside knowledge.

POLICY EXCERPTS:
{context}

QUESTION: {question}

Answer concisely, and cite the section number(s) you used."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text, response.usage.input_tokens, response.usage.output_tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true",
                         help="Also call the LLM to generate answers and count real tokens (costs API credits)")
    args = parser.parse_args()

    client = get_client()
    collection = get_or_create_collection(client)
    bm25_index, chunks = build_bm25_index()

    architectures = ["naive", "hybrid", "agentic"]
    # stats[architecture][category] -> list of per-question result dicts
    stats = {arch: defaultdict(list) for arch in architectures}

    print(f"Running {len(TEST_QUESTIONS)} questions x {len(architectures)} architectures"
          f"{' (with generation)' if args.generate else ' (retrieval only)'}...\n")

    for q in TEST_QUESTIONS:
        qid, category, question, expected = q["id"], q["category"], q["question"], q["expected_chunk_ids"]

        # naive
        results, elapsed = run_naive(collection, question)
        hit = is_hit(expected, results)
        answer, in_tok, out_tok = maybe_generate(question, results, args.generate)
        stats["naive"][category].append({
            "id": qid, "hit": hit, "latency": elapsed,
            "input_tokens": in_tok, "output_tokens": out_tok,
        })

        # hybrid
        results, elapsed = run_hybrid(collection, bm25_index, chunks, question)
        hit = is_hit(expected, results)
        answer, in_tok, out_tok = maybe_generate(question, results, args.generate)
        stats["hybrid"][category].append({
            "id": qid, "hit": hit, "latency": elapsed,
            "input_tokens": in_tok, "output_tokens": out_tok,
        })

        # agentic
        results, elapsed, reasoning_log = run_agentic(collection, bm25_index, chunks, question)
        hit = is_hit(expected, results)
        answer, in_tok, out_tok = maybe_generate(question, results, args.generate)
        stats["agentic"][category].append({
            "id": qid, "hit": hit, "latency": elapsed,
            "input_tokens": in_tok, "output_tokens": out_tok,
        })

        print(f"  {qid} ({category}): naive={'OK' if stats['naive'][category][-1]['hit'] else 'MISS'}  "
              f"hybrid={'OK' if stats['hybrid'][category][-1]['hit'] else 'MISS'}  "
              f"agentic={'OK' if stats['agentic'][category][-1]['hit'] else 'MISS'}")

    # ---- Build comparison table ----
    print("\n" + "=" * 78)
    print(f"{'Architecture':<12}{'Accuracy':<12}{'Avg Latency':<14}{'Avg In Tok':<12}{'Avg Out Tok':<12}")
    print("-" * 78)
    for arch in architectures:
        all_results = [r for cat_list in stats[arch].values() for r in cat_list]
        n = len(all_results)
        hits = sum(r["hit"] for r in all_results)
        avg_latency = sum(r["latency"] for r in all_results) / n
        avg_in = sum(r["input_tokens"] for r in all_results) / n
        avg_out = sum(r["output_tokens"] for r in all_results) / n
        print(f"{arch:<12}{hits}/{n:<10}{avg_latency:.3f}s{'':<8}{avg_in:<12.0f}{avg_out:<12.0f}")

    print("\nBy category:")
    print(f"{'Architecture':<12}{'general':<12}{'citation':<12}{'multi_hop':<12}")
    print("-" * 48)
    for arch in architectures:
        row = f"{arch:<12}"
        for cat in ["general", "citation", "multi_hop"]:
            cat_results = stats[arch].get(cat, [])
            n = len(cat_results)
            hits = sum(r["hit"] for r in cat_results)
            row += f"{hits}/{n:<10}"
        print(row)


if __name__ == "__main__":
    main()
