
import os
import chromadb

# ⚠️ القيم دي جاية من صاحبة الـ RAG (chroma_db في جذر الريبو، مش جوه db/)
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "brightpeak_policies"

# نفس filter مبني على policy_type -- عدّلناها هنا لسياسات التخرج بدل المنح
SCHOLARSHIP_POLICY_TYPE = "graduation_policy"


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
        # فشل الاتصال بمخزن الـ RAG مش سبب كافي نوقف طلب المنحة كله --
        # بيرجع فاضي والـ node بيكمل من غير سياق سياسة (ويُسجَّل في اللوج).
        return ""