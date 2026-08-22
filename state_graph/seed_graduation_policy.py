"""
state_graph/seed_graduation_policy.py

One-time script: adds a "graduation requirements" policy document into the
shared team Chroma vector store, so retrieve_scholarship_policy in
rag_client.py has something real to pull instead of returning empty.

Run (from inside state_graph/):
    python seed_graduation_policy.py
"""

import os
import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "brightpeak_policies"

POLICY_TEXT = (
    "Graduation Requirements Policy -- Brightpeak Academy: "
    "For a student to be considered eligible for graduation from their "
    "department, they must have completed the minimum number of required "
    "credit hours for their department, and their cumulative GPA must meet "
    "or exceed the minimum required for that department. In addition, the "
    "student must have no outstanding financial dues, no pending library "
    "debts or fines, and must have uploaded and had verified all required "
    "documents for the graduation file before the request is escalated to "
    "final administrative approval."
)


def main():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    collection.upsert(
        ids=["graduation-policy-001"],
        documents=[POLICY_TEXT],
        metadatas=[{
            "policy_type": "graduation_policy",
            "document_id": "graduation-policy",
            "section_id": "001",
            "section_title": "General Graduation Requirements",
        }],
    )

    print(">>> Graduation policy document added successfully at:", CHROMA_PATH)
    print(">>> Documents currently in the collection:", collection.count())


if __name__ == "__main__":
    main()