
from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from .tool_registry import TOOL_REGISTRY


class AssessProfileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int


class RoleRequirementsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_title: str


class CourseSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_tags: list[str] = Field(
        default_factory=list,
        description="Lowercase, underscore-separated skill tags to match, e.g. 'data_visualization' not 'Data Visualization'.",
    )
    max_price: float | None = None
    max_weekly_hours: float | None = None
    after_date: str | None = Field(
        default=None,
        description=(
            "Only courses whose start_date is on/after this value. This is NOT the "
            "student's target completion deadline -- leave it null unless the request "
            "explicitly says the student can't start before some date."
        ),
    )


class PrerequisiteCheckArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int
    course_id: int


class SaveGoalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int
    target_role_title: str
    weekly_hours_available: float
    budget: float
    target_date: str | None = None


class EnrollArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int
    course_id: int


ARG_SCHEMA_BY_TOOL: dict[str, type[BaseModel]] = {
    "get_student_profile": AssessProfileArgs,
    "get_role_requirements": RoleRequirementsArgs,
    "search_courses": CourseSearchArgs,
    "check_prerequisites": PrerequisiteCheckArgs,
    "save_learning_goal": SaveGoalArgs,
    "enroll_student": EnrollArgs,
}


def _resolve_student_email(student_id: int) -> str:
    """get_student_profile only accepts an email, not a student_id -- bridge
    the two the same way agent/main.py's _get_student_email() already does
    for the Memory/RAG agent, reusing server.py's own connection helper
    rather than duplicating its logic."""
    from mcp_server.server import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"No student found with student_id={student_id}")
    return row["email"]


def call_real_tool(tool_name: str, llm: BaseChatModel, goal: str, instruction: str, context: str) -> str:
    """Extract structured arguments for `tool_name` from the goal/instruction/
    prior sub-task outputs, call the real MCP tool, and return its JSON
    result as the task's output string (grounded -- not model-generated
    prose standing in for a real call)."""
    schema = ARG_SCHEMA_BY_TOOL.get(tool_name)
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if schema is None or tool_fn is None:
        raise ValueError(f"No registered schema/function for expected_tool={tool_name!r}")

    args = llm.with_structured_output(schema, method="json_schema").invoke([
        (
            "system",
            f"Extract the exact arguments needed to call the '{tool_name}' tool. "
            "Use only values stated or clearly implied by the goal and prior outputs. "
            "Never invent an id, email, or date that isn't grounded in the given text.",
        ),
        (
            "human",
            f"Goal: {goal}\nCurrent sub-task: {instruction}\nPrior outputs:\n{context}",
        ),
    ], temperature=0.0)

    kwargs = args.model_dump()
    if tool_name == "get_student_profile":
        
        student_id = kwargs.pop("student_id")
        kwargs["email"] = _resolve_student_email(student_id)

    result = tool_fn(**kwargs)
    return json.dumps(result, ensure_ascii=False)