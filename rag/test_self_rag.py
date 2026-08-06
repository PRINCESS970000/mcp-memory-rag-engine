from self_rag_check import verify, flag_if_unsupported
from naive_rag import naive_rag_search
from vector_store import get_client, get_or_create_collection
from generate import generate_answer

client = get_client()
collection = get_or_create_collection(client)

question = "What counts as valid grounds for a grade appeal?"
results = naive_rag_search(collection, question)
answer = generate_answer(question, [c for c, _ in results])

result = verify(question, answer, results)
print("Relevance passed:", result.relevance_passed)
print("Support passed:", result.support_passed)
print()
print(flag_if_unsupported(result, answer))
