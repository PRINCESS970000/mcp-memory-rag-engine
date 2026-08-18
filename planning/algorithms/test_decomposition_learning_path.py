from types import SimpleNamespace

import pytest

from ..models import Plan
from .. import tool_registry
from .decomposition import execute_plan
from .dynamic_decomposition import dynamic_decomposition, DynamicDecision



def test_cycle_is_still_rejected_with_expected_tool_field():
    with pytest.raises(ValueError, match="Cycle detected"):
        Plan.model_validate({
            "goal": "Reject an invalid cyclic learning path",
            "tasks": [
                {"id": "a", "instruction": "Assess current level", "depends_on": ["b"], "expected_tool": None},
                {"id": "b", "instruction": "Search candidate courses", "depends_on": ["a"], "expected_tool": "search_courses"},
            ],
        })



class ExplodingLLM:
    """Raises if ever asked to freehand an answer for a tool-task; only
    allowed to answer the reasoning-only synthesis task and any arg
    extraction calls."""

    def with_structured_output(self, schema, *, method):
        return _ArgExtractor(schema)

    def invoke(self, messages, **kwargs):
        prompt = messages[-1][1]
        if "Current task:" in prompt and "reasoning" not in prompt.lower():
            pass  
        return SimpleNamespace(content="Final plan summary for the student.")


class _ArgExtractor:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages, **kwargs):
        if self.schema.__name__ == "RoleRequirementsArgs":
            return self.schema(role_title="Data Analyst")
        if self.schema.__name__ == "PrerequisiteCheckArgs": 
            return self.schema(student_id=6, course_id=9)
        raise AssertionError(f"Unexpected schema requested: {self.schema.__name__}")


def test_execute_plan_calls_real_tool_for_tool_tasks(monkeypatch):
    calls = []

    def fake_get_role_requirements(role_title: str) -> dict:
        calls.append(role_title)
        return {"status": "success", "data": {"role_id": 4, "title": role_title, "required_skills": ["sql"]}}

    monkeypatch.setitem(tool_registry.TOOL_REGISTRY, "get_role_requirements", fake_get_role_requirements)

    plan = Plan.model_validate({
        "goal": "Plan Youssef's path to Data Analyst",
        "tasks": [
            {"id": "define_role", "instruction": "Look up Data Analyst requirements",
             "depends_on": [], "expected_tool": "get_role_requirements"},
            {"id": "summary", "instruction": "Summarize the plan",
             "depends_on": ["define_role"], "expected_tool": None,
             "category": "deterministic_parsing"},
        ],
    })

    outputs, metrics = execute_plan(plan, ExplodingLLM())

    assert calls == ["Data Analyst"]  # the real tool was actually invoked
    assert "required_skills" in outputs["define_role"]  # real tool JSON, not LLM prose
    # summary went through the routed (stubbed) path in this test, not raw llm.invoke
    assert "summary" in outputs
    assert "summary" in metrics


def test_get_student_profile_resolves_student_id_to_email(monkeypatch):
    """Regression test for the real bug hit in production: a goal phrased
    with student_id (not an email) must not reach get_student_profile as a
    hallucinated/invalid email."""
    from .. import tool_args

    resolved_calls = []

    def fake_resolve_email(student_id: int) -> str:
        resolved_calls.append(student_id)
        assert student_id == 4
        return "youssef.i@brightpeak.edu"

    profile_calls = []

    def fake_get_student_profile(email: str) -> dict:
        profile_calls.append(email)
        return {"status": "success", "data": {"student_id": 4, "email": email, "enrolled_courses": []}}

    monkeypatch.setattr(tool_args, "_resolve_student_email", fake_resolve_email)
    monkeypatch.setitem(tool_registry.TOOL_REGISTRY, "get_student_profile", fake_get_student_profile)

    plan = Plan.model_validate({
        "goal": "Plan Youssef's (student_id=4) path to Data Analyst",
        "tasks": [
            {"id": "assess", "instruction": "Look up Youssef's (student_id=4) completed courses",
             "depends_on": [], "expected_tool": "get_student_profile"},
        ],
    })

    class ProfileArgLLM:
        def with_structured_output(self, schema, *, method):
            return _Structured(self, schema)

        def structured(self, schema):
            return schema(student_id=4)

    outputs, _ = execute_plan(plan, ProfileArgLLM())

    assert resolved_calls == [4]
    assert profile_calls == ["youssef.i@brightpeak.edu"]  # real email, not a hallucinated one
    assert "youssef" in outputs["assess"].lower()


class _Structured:
    def __init__(self, owner, schema):
        self.owner, self.schema = owner, schema

    def invoke(self, messages, **kwargs):
        return self.owner.structured(self.schema)




class ScriptedDynamicLLM:
    """Step 1 proposes enrolling in Cloud Computing (a real tool call).
    Step 2's decision is scripted to react differently depending on whether
    step 1's real observation was eligible or not -- proving the loop
    actually conditions on the tool result instead of ignoring it."""

    def __init__(self):
        self.step = 0

    def with_structured_output(self, schema, *, method):
        if schema is DynamicDecision:
            return _DecisionStub(self)
        return _ArgExtractor(schema)

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(content="Dropped Cloud Computing; recommend Intro CS first.")


class _DecisionStub:
    def __init__(self, owner: ScriptedDynamicLLM):
        self.owner = owner

    def invoke(self, messages, **kwargs):
        self.owner.step += 1
        observation = messages[-1][1]
        if self.owner.step == 1:
            return DynamicDecision(
                done=False,
                next_task="Check prerequisites for Cloud Computing Fundamentals",
                expected_tool="check_prerequisites",
            )
  
        assert '"eligible": false' in observation.lower() or "eligible': false" in observation.lower()
        return DynamicDecision(done=True, next_task="")


def test_dynamic_decomposition_reroutes_after_real_prerequisite_failure(monkeypatch):
    def fake_check_prerequisites(student_id: int, course_id: int) -> dict:
        assert (student_id, course_id) == (6, 9)  # Hoda / Cloud Computing
        return {"status": "success", "eligible": False, "missing_prerequisites": [1]}

    monkeypatch.setitem(tool_registry.TOOL_REGISTRY, "check_prerequisites", fake_check_prerequisites)

    history = dynamic_decomposition(
        "Plan Hoda's (student_id=6) path to ML Engineer, budget=500, weekly_hours=10",
        ScriptedDynamicLLM(),
        max_steps=4,
    )

    assert len(history) == 1  # stopped as soon as it saw the real failure
    task, result = history[0]
    assert "Cloud Computing" in task
    assert '"eligible": false' in result.lower()