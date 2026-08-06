from chunk_schema import PolicyChunk
from ingest import load_all_policies
from vector_store import get_client, get_or_create_collection, query as vector_query


def naive_rag_search(collection, question: str, n_results: int = 3) -> list[tuple[PolicyChunk, float]]:
    """
    Baseline naive RAG: embed the question, do plain vector similarity search,
    no keyword matching, no multi-hop reasoning, no filtering.

    Returns (chunk, similarity_score) pairs, same shape as hybrid_search's
    return value, so both can be run through the same eval loop later.
    """
    all_chunks = {c.chunk_id: c for c in load_all_policies()}

    results = vector_query(collection, question, n_results=n_results)

    ids = results["ids"][0]
    # Chroma returns cosine *distance*; convert to similarity (higher = better)
    # so naive RAG's scores read the same direction as BM25/RRF scores.
    distances = results["distances"][0]
    similarities = [1 - d for d in distances]

    return [(all_chunks[chunk_id], score) for chunk_id, score in zip(ids, similarities)]