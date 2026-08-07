from loop import handle_message
from short_term import ShortTermMemory

stm = ShortTermMemory(session_id="demo_session", student_id=7)

r1 = handle_message(stm, student_id=7, message="What are the valid grounds for filing a grade appeal?")
print("--- POLICY QUESTION ---")
print("Intent:", r1["intent"])
print("Answer:", r1["answer"])
print("Verification:", r1["verification"])

r2 = handle_message(stm, student_id=7, message="What did we decide last time about my re-enrollment?")
print()
print("--- MEMORY QUESTION ---")
print("Intent:", r2["intent"])
print("Answer:", r2["answer"])
print("Memory status:", r2["memory_status"])
