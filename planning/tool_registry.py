
from __future__ import annotations

from typing import Callable

try:
    from mcp_server.server import (
        get_student_profile,
        get_role_requirements,
        search_courses,
        check_prerequisites,
        save_learning_goal,
        enroll_student,
    )
except ImportError:  # pragma: no cover - exercised only outside the real repo
    # Allows this module (and anything importing it) to be unit-tested
    # without the full mcp_server/ package on the path. Replace/remove once
    # wired into the real repo.
    def get_student_profile(email: str) -> dict: ...
    def get_role_requirements(role_title: str) -> dict: ...
    def search_courses(skill_tags=None, max_price=None, max_weekly_hours=None, after_date=None) -> dict: ...
    def check_prerequisites(student_id: int, course_id: int) -> dict: ...
    def save_learning_goal(student_id: int, target_role_title: str, weekly_hours_available: float, budget: float, target_date: str = None) -> dict: ...
    def enroll_student(student_id: int, course_id: int) -> dict: ...


# expected_tool string (used in the DAG / DynamicDecision) -> real function
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "get_student_profile": get_student_profile,
    "get_role_requirements": get_role_requirements,
    "search_courses": search_courses,
    "check_prerequisites": check_prerequisites,
    "save_learning_goal": save_learning_goal,
    "enroll_student": enroll_student,
}