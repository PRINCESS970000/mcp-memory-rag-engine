import os
import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "chroma_store")
COLLECTION_NAME = "brightpeak_policies"

INTERNSHIP_POLICY_TYPE = "internship_readiness"


def retrieve_internship_policy(query: str, top_k: int = 3) -> str:
    """
    بيرجع نص السياسة/متطلبات الوظيفة المرتبطة بالسؤال، كسياق (policy_context)
    قبل قرار الجاهزية للتقديم.

    لو المخزن فاضي أو مفيش نتائج، بيرجع نص فاضي -- الـ node هو المسؤول عن
    التعامل مع الحالة دي (مايوقفش الـ graph كله).
    """
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection(COLLECTION_NAME)

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"policy_type": INTERNSHIP_POLICY_TYPE},
        )

        documents = results.get("documents", [[]])[0]
        if not documents:
            return ""

        return "\n---\n".join(documents)

    except Exception:
        return ""