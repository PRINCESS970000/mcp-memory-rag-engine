import os
import uuid
import chromadb
 
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
COLLECTION_NAME = "brightpeak_policies"
 
 
def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(COLLECTION_NAME)
 
 
def list_documents() -> list:
    collection = _get_collection()
    results = collection.get()
    docs = []
    for i, doc_id in enumerate(results["ids"]):
        docs.append({
            "id": doc_id,
            "text": results["documents"][i],
            "metadata": results["metadatas"][i] if results["metadatas"] else {},
        })
    return docs
 
 
def add_document(text: str, policy_type: str, section_title: str = "") -> dict:
    collection = _get_collection()
    doc_id = f"{policy_type}-{uuid.uuid4().hex[:8]}"
    collection.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[{"policy_type": policy_type, "section_title": section_title}],
    )
    return {"id": doc_id}
 
 
def delete_document(doc_id: str) -> None:
    collection = _get_collection()
    collection.delete(ids=[doc_id])