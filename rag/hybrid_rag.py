from rank_bm25 import BM25Okapi

from ingest import load_all_policies


def build_bm25_index():
    """
    Builds a BM25 index over the same 44 chunks used in the vector store.
    Returns (bm25_index, chunks) -- chunks is kept in the same order as the
    index so BM25 result positions can be mapped back to chunk_ids.
    """
    chunks = load_all_policies()
    tokenized_corpus = [c.embedding_text().lower().split() for c in chunks]
    bm25_index = BM25Okapi(tokenized_corpus)
    return bm25_index, chunks


def bm25_search(bm25_index, chunks, question: str, n_results: int = 3):
    """Returns the top-n chunks by BM25 score, as (chunk, score) pairs."""
    tokenized_query = question.lower().split()
    scores = bm25_index.get_scores(tokenized_query)

    scored_chunks = list(zip(chunks, scores))
    scored_chunks.sort(key=lambda pair: pair[1], reverse=True)

    return scored_chunks[:n_results]

from vector_store import get_client, get_or_create_collection, query as vector_query

RRF_K = 60


def hybrid_search(collection, bm25_index, chunks, question: str, n_results: int = 3):
    """
    Combines vector search and BM25 using Reciprocal Rank Fusion (RRF).
    RRF combines by rank position, not raw score, since cosine similarity
    and BM25 scores live on completely different scales and can't be
    averaged directly.
    """
    # Get more candidates than we need from each method, so fusion has room to work
    vector_results = vector_query(collection, question, n_results=10)
    vector_ids_ranked = vector_results["ids"][0]

    bm25_ranked = bm25_search(bm25_index, chunks, question, n_results=10)
    bm25_ids_ranked = [chunk.chunk_id for chunk, _score in bm25_ranked]

    rrf_scores: dict[str, float] = {}
    for rank, chunk_id in enumerate(vector_ids_ranked):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (RRF_K + rank)
    for rank, chunk_id in enumerate(bm25_ids_ranked):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (RRF_K + rank)

    ranked_chunk_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:n_results]

    chunks_by_id = {c.chunk_id: c for c in chunks}
    return [(chunks_by_id[cid], rrf_scores[cid]) for cid in ranked_chunk_ids]