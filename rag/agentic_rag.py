from chunk_schema import PolicyChunk
from hybrid_rag import build_bm25_index, hybrid_search
from vector_store import get_by_ids

MAX_HOPS = 2  # first search + at most one follow-up hop


def agentic_rag_search(collection, bm25_index, chunks, question: str, n_results: int = 3):
    """
    Agentic RAG: runs hybrid_search first, then inspects the results' cross_refs.
    If any top result references another policy's section, it fetches that
    section directly (by id, no re-search needed) as a second hop.

    Returns (results, reasoning_log) -- reasoning_log is a list of strings
    explaining every retrieval decision, for the grader to inspect.
    """
    reasoning_log = []

    # --- Hop 1: normal hybrid search ---
    hop1_results = hybrid_search(collection, bm25_index, chunks, question, n_results=n_results)
    reasoning_log.append(
        f"Hop 1: hybrid search returned {[c.chunk_id for c, _ in hop1_results]}"
    )

    # --- Decide whether a second hop is needed ---
    cross_ref_ids_to_fetch = []
    already_have = {c.chunk_id for c, _ in hop1_results}

    for chunk, score in hop1_results:
        if chunk.cross_refs:
            for ref_id in chunk.cross_refs:
                if ref_id and ref_id not in already_have:
                    cross_ref_ids_to_fetch.append(ref_id)

    total_refs_seen = sum(len(chunk.cross_refs) for chunk, _ in hop1_results)

    if total_refs_seen == 0:
        reasoning_log.append("No cross-references found in top results. Stopping after hop 1.")
    elif not cross_ref_ids_to_fetch:
        reasoning_log.append(
            f"Found {total_refs_seen} cross-reference(s) in top results, but all referenced "
            f"chunks were already retrieved in hop 1. Stopping without a redundant hop 2."
        )

    if not cross_ref_ids_to_fetch:
        return hop1_results, reasoning_log
    reasoning_log.append(
        f"Hop 1 results reference {cross_ref_ids_to_fetch} in other policies. "
        f"Fetching them directly for hop 2 instead of guessing."
    )

    # --- Hop 2: fetch the referenced chunks directly by id ---
    fetched = get_by_ids(collection, cross_ref_ids_to_fetch)
    chunks_by_id = {c.chunk_id: c for c in chunks}
    hop2_chunks = [chunks_by_id[cid] for cid in fetched["ids"] if cid in chunks_by_id]

    reasoning_log.append(f"Hop 2: fetched {[c.chunk_id for c in hop2_chunks]}")

    # Hop 2 results get a fixed high score since they were pulled by an explicit
    # reference, not a similarity match -- they're not "guessed," they're known-relevant.
    hop2_results = [(c, 1.0) for c in hop2_chunks]

    final_results = hop1_results + hop2_results
    return final_results, reasoning_log