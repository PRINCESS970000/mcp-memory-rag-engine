"""
Runs the full Kareem re-enrollment story once, end to end:
3 initial events + consolidation + 1 reversal event + consolidation again.
This is the clean demo script — safe to show as-is in the README/demo.
"""

from episodic_store import log_event, get_events_for_student
from consolidation import consolidate_student

print("--- Logging initial events ---")
log_event(7, "call_1", "re_enrollment_decision",
    "Kareem requested re-enrollment in CS101 after drop. Admin decision: DENIED - must wait one semester.")
log_event(7, "call_2", "re_enrollment_decision",
    "Kareem asked again about re-enrollment in CS101. Admin decision: DENIED - same policy applies.")
log_event(7, "call_3", "re_enrollment_decision",
    "Kareem submitted medical documentation. Admin decision: APPROVED - exception granted for re-enrollment in CS101.")

print("\n--- First consolidation (no conflict yet, first fact) ---")
result1 = consolidate_student(7, "re_enrollment_decision", "CS101 re-enrollment")
print(result1)

print("\n--- Admin reverses the decision (new conflicting event) ---")
log_event(7, "call_4", "re_enrollment_decision",
    "Admin review reversed the decision. New decision: DENIED - medical documentation was insufficient.")

print("\n--- Second consolidation (should detect and resolve conflict) ---")
result2 = consolidate_student(7, "re_enrollment_decision", "CS101 re-enrollment")
print(result2)