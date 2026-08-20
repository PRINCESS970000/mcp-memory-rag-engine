import os
import chromadb
 
from chunk_schema import PolicyChunk
 
# 
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "chroma_store")
COLLECTION_NAME = "brightpeak_policies"


SCHOLARSHIP_POLICY_TYPE = "scholarship_eligibility"
 
 
def retrieve_scholarship_policy(query: str, top_k: int = 3) -> str:
    """
    بيرجع نص سياسة الأهلية المرتبط بالسؤال/الطلب، كسياق (policy_context)
    يتحط في الـ state قبل قرار الموافقة على الطلب.
 
    لو المخزن فاضي أو مفيش نتائج، بيرجع نص فاضي -- الـ node اللي بينادي
    الدالة دي هو المسؤول عن التعامل مع الحالة دي (مايوقفش الـ graph كله).
    """
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection(COLLECTION_NAME)
 
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"policy_type": SCHOLARSHIP_POLICY_TYPE},
        )
 
        documents = results.get("documents", [[]])[0]
        if not documents:
            return ""
 
        return "\n---\n".join(documents)
 
    except Exception:
     
        return ""