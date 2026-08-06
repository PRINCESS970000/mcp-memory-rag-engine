import chromadb
from chromadb.config import Settings

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "brightpeak_policies"


def get_client() -> chromadb.PersistentClient:
    """Returns a persistent Chroma client that writes to ./chroma_db on disk."""
    return chromadb.PersistentClient(path=CHROMA_PATH)


def get_or_create_collection(client: chromadb.PersistentClient):
    """
    Creates (or reopens) the policy collection with an explicit HNSW config.
    space='cosine' matches how sentence embeddings are typically compared.
    """
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 100,   # higher = better index quality, slower build
            "hnsw:M": 16,                  # graph connectivity; 16 is a solid default
        },
    )

from chunk_schema import PolicyChunk


def add_chunks(collection, chunks: list[PolicyChunk]) -> None:
    """
    Embeds and inserts PolicyChunk objects into the collection.
    Uses upsert (not add) so re-running ingestion is safe and idempotent --
    running it twice won't create duplicate entries.
    """
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.embedding_text() for c in chunks],
        metadatas=[c.to_metadata_payload() for c in chunks],
    )

def query(collection, question: str, n_results: int = 3, where: dict | None = None):
    """
    Basic similarity search, with optional metadata pre-filtering via `where`.
    Example: where={"policy_type": "grade_appeal"} restricts the ANN search
    to only that policy's chunks -- this is the pre-filter the rubric requires.
    """
    return collection.query(
        query_texts=[question],
        n_results=n_results,
        where=where,
    )    

def get_by_ids(collection, chunk_ids: list[str]):
    """Fetches specific chunks by their known chunk_id -- no similarity search involved."""
    if not chunk_ids:
        return []
    return collection.get(ids=chunk_ids)