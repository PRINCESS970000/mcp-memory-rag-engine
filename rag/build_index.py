"""
Builds (or rebuilds) the Chroma vector index from every policy file in
policies/. Safe to re-run: add_chunks() uses upsert, so existing chunk_ids
get updated in place rather than duplicated.

Usage (run from inside rag/):
    python build_index.py
"""

from ingest import load_all_policies
from vector_store import get_client, get_or_create_collection, add_chunks


def main():
    chunks = load_all_policies()
    print(f"Loaded {len(chunks)} chunks from policies/")

    client = get_client()
    collection = get_or_create_collection(client)

    add_chunks(collection, chunks)
    print(f"Upserted {len(chunks)} chunks into Chroma collection "
          f"'{collection.name}' (now {collection.count()} total chunks in index)")


if __name__ == "__main__":
    main()
