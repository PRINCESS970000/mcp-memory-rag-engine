import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


from types import SimpleNamespace

import pytest

from planning.algorithms import (
    Environment,
    grounded_path_checks,
    execute_plan,
    final_output,
    flatten_lats_tree,
    lats,
    reflexion,
)
from planning.models import EnvironmentFeedback, Plan
from planning.algorithms.decomposition import GeneratedPlan
from planning.algorithms.dynamic_decomposition import DynamicDecision
from planning.algorithms.lats import LATSActionBatch, ValueEstimate
from planning.algorithms.tree_of_thoughts import ThoughtCandidates, ThoughtEvaluation
from planning.algorithms.routing import route_and_execute_subtask
from langchain_mistralai import ChatMistralAI


# ---------------------------------------------------------------------------
# Shared fixtures: a small, self-consistent fake BrightPeak catalog so tests
# don't need a live db/brightpeak.db or a real MISTRAL_API_KEY.
# ---------------------------------------------------------------------------

def fake_catalog_data() -> dict:
    return {
        "learning_goal": {
            "budget": 500,
            "weekly_hours_available": 10,
            "target_date": "2026-12-31",
        },
        "courses": [
            {
                "course_id": 1, "title": "Python Basics", "price": 100,
                "weekly_hours": 5, "start_date": "2026-09-01", "end_date": "2026-09-29",
                "difficulty": "beginner", "skill_tags": "python,programming",
            },
            {
                "course_id": 2, "title": "SQL for Data Analysis", "price": 130,
                "weekly_hours": 4, "start_date": "2026-10-01", "end_date": "2026-10-29",
                "difficulty": "beginner", "skill_tags": "sql,data_analysis",
            },
        ],
        "prerequisites": [],
        "completed_course_ids": [],
        "required_skills": ["python", "sql"],
    }


class FakeEnvironment:
    """Same interface as the real Environment, without touching the db or
    the MCP server -- used wherever a test needs an Environment but isn't
    specifically testing Environment.evaluate()'s grounded logic itself."""

    def __init__(self, catalog_data: dict, feedback_sequence: list[EnvironmentFeedback] | None = None):
        self._catalog_data = catalog_data
        self._feedback_sequence = iter(feedback_sequence) if feedback_sequence else None

    def get_catalog_data(self) -> dict:
        return self._catalog_data

    def evaluate(self, state) -> EnvironmentFeedback:
        if self._feedback_sequence is not None:
            return next(self._feedback_sequence)
        return EnvironmentFeedback(success=True, score=1.0, details=[])


class RecordingLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, messages, **kwargs):
        human_prompt = messages[-1][1]
        self.prompts.append(human_prompt)
        return SimpleNamespace(content=f"MARKER_OUTPUT_{len(self.prompts)}")


# ---------------------------------------------------------------------------
# Decomposition-first DAG: construction, cycle rejection, execution order.
# Domain-agnostic Plan/Task model, unaffected by the BrightPeak adaptation.
# ---------------------------------------------------------------------------

def test_dag_order_and_parallel_batches():
    plan = Plan.model_validate({
        "goal": "Prepare a useful launch brief",
        "tasks": [
            {"id": "research", "instruction": "Research the audience", "depends_on": []},
            {"id": "risks", "instruction": "Identify launch risks", "depends_on": []},
            {"id": "brief", "instruction": "Synthesize the launch brief", "depends_on": ["research", "risks"]},
        ],
    })
    assert plan.execution_batches() == [["research", "risks"], ["brief"]]
    assert plan.topological_order()[-1] == "brief"


def test_cycle_is_rejected():
    with pytest.raises(ValueError, match="Cycle detected"):
        Plan.model_validate({
            "goal": "Reject an invalid cyclic plan",
            "tasks": [
                {"id": "a", "instruction": "Perform task alpha", "depends_on": ["b"]},
                {"id": "b", "instruction": "Perform task beta", "depends_on": ["a"]},
            ],
        })


def test_executor_passes_dependency_outputs():
    plan = Plan.model_validate({
        "goal": "Create a concise combined report",
        "tasks": [
            {"id": "a", "instruction": "Collect useful evidence", "depends_on": [], "category": "deterministic_parsing"},
            {"id": "b", "instruction": "Synthesize all evidence", "depends_on": ["a"], "category": "deterministic_parsing"},
        ],
    })
    llm = RecordingLLM()
    environment = FakeEnvironment(fake_catalog_data())
    outputs, metrics_by_task = execute_plan(plan, llm, environment)

    assert "MARKER_OUTPUT_1" in llm.prompts[1]  # task b's context embeds task a's output
    assert final_output(plan, outputs) == outputs["b"]
    assert metrics_by_task["a"]["routed_algorithm"] == "Plan-and-Solve"
    assert metrics_by_task["b"]["routed_algorithm"] == "Plan-and-Solve"


# ---------------------------------------------------------------------------
# Self-Refine: grounded_path_checks() -- deterministic, no LLM, catches
# hallucinated courses and wrong totals that an ungrounded self-critique
# would miss (see planning_eval/ for the full documented case).
# ---------------------------------------------------------------------------

def test_grounded_path_checks_catch_wrong_total_and_hallucinated_course():
    all_courses = [
        {"course_id": 1, "title": "Python Basics", "price": 100},
        {"course_id": 2, "title": "SQL for Data Analysis", "price": 130},
        {"course_id": 3, "title": "Deep Learning Foundations", "price": 450},
    ]
    path_courses = [all_courses[0], all_courses[1]]  # Python Basics + SQL, true total = 230

    draft = (
        "Your recommended path is Python Basics and Deep Learning Foundations, "
        "for a total cost of $999."
    )
    issues = grounded_path_checks(draft, path_courses, all_courses, total_price=230)

    # 1) SQL for Data Analysis is in the real path but never mentioned.
    assert any("SQL for Data Analysis" in issue for issue in issues)
    # 2) Deep Learning Foundations is mentioned but NOT in the real path (hallucinated).
    assert any("Deep Learning Foundations" in issue and "NOT part of" in issue for issue in issues)
    # 3) The stated $999 doesn't match the real total of $230.
    assert any("correct total cost" in issue for issue in issues)


def test_grounded_path_checks_pass_on_accurate_draft():
    all_courses = [
        {"course_id": 1, "title": "Python Basics", "price": 100},
        {"course_id": 2, "title": "SQL for Data Analysis", "price": 130},
    ]
    draft = "Your path is Python Basics and SQL for Data Analysis, totalling $230.00."
    issues = grounded_path_checks(draft, all_courses, all_courses, total_price=230)
    assert issues == []


def test_grounded_path_checks_do_not_flag_already_completed_courses_as_hallucinated():
    """Regression test: a course the student already completed/enrolled in
    and that's mentioned purely as background context must not be flagged
    as 'hallucinated' just because it isn't part of the new recommended
    path -- this false positive is what previously sent the revision step
    spiraling into inventing several unrelated extra courses to try to
    'fix' something that was never actually wrong."""
    all_courses = [
        {"course_id": 1, "title": "Introduction to Computer Science", "price": 150},
        {"course_id": 2, "title": "Advanced Machine Learning", "price": 400},
        {"course_id": 3, "title": "Database Management Systems", "price": 250},
        {"course_id": 4, "title": "Software Engineering Principles", "price": 200},
    ]
    path_courses = [all_courses[3]]  # only Software Engineering Principles is newly recommended
    draft = (
        "Omar has completed Introduction to Computer Science and Database Management "
        "Systems, and is enrolled in Advanced Machine Learning. We recommend Software "
        "Engineering Principles next, for a total of $200.00."
    )

    issues = grounded_path_checks(
        draft, path_courses, all_courses, total_price=200,
        already_known_course_ids={1, 2, 3},
    )
    assert issues == []


# ---------------------------------------------------------------------------
# Grounded Environment: real prerequisite/budget/skill-coverage checks
# against fake-but-realistic catalog data, no DB or MCP server involved
# (the private cache is seeded directly, bypassing _fetch_data()).
# ---------------------------------------------------------------------------

def _environment_with_data(data: dict) -> Environment:
    environment = Environment(student_id=999)  # no mcp_server_path -> never touches the DB
    environment._data_cache = data
    return environment


def test_environment_rejects_path_missing_a_prerequisite():
    data = fake_catalog_data()
    data["prerequisites"] = [{"course_id": 2, "prerequisite_course_id": 1}]  # course 2 needs course 1
    environment = _environment_with_data(data)

    feedback = environment.evaluate([2])  # course 1 neither completed nor in the path
    assert feedback.success is False
    assert any("requires course 1" in issue for issue in feedback.details)


def test_environment_accepts_a_valid_path():
    data = fake_catalog_data()
    environment = _environment_with_data(data)

    feedback = environment.evaluate([1, 2])  # covers python+sql, within budget/hours/deadline
    assert feedback.success is True
    assert feedback.score == 1.0


def test_environment_rejects_path_over_budget():
    data = fake_catalog_data()
    data["learning_goal"]["budget"] = 50  # both courses together cost 230
    environment = _environment_with_data(data)

    feedback = environment.evaluate([1, 2])
    assert feedback.success is False
    assert any("exceeding the budget" in issue for issue in feedback.details)


# ---------------------------------------------------------------------------
# Reflexion: multi-trial retry with a capped episodic memory buffer,
# grounded against the real Environment.evaluate(). llm.invoke() mocked
# directly (matching the BaseChatModel convention every algorithm in this
# package now shares) -- no network call or API key needed.
# ---------------------------------------------------------------------------

class SequencedLLM:
    """Returns each response in order on successive .invoke() calls,
    matching langchain's AIMessage shape (content + response_metadata)."""

    def __init__(self, contents: list[str]):
        self._responses = iter(contents)

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(
            content=next(self._responses),
            response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 5}},
        )


def test_reflexion_retries_with_bounded_memory():
    catalog_data = fake_catalog_data()
    catalog_data["prerequisites"] = [{"course_id": 2, "prerequisite_course_id": 1}]

    environment = FakeEnvironment(catalog_data, feedback_sequence=[
        EnvironmentFeedback(success=False, score=0.3, details=["Course 2 requires course 1."]),
        EnvironmentFeedback(success=True, score=1.0, details=[]),
    ])

    llm = SequencedLLM([
        "[2]",                                                            # trial 1: missing the prerequisite
        "I forgot course 1 is a prerequisite of course 2; I will add it first.",
        "[1, 2]",                                                         # trial 2: applies the lesson
    ])

    result = reflexion(environment, catalog_data, llm, max_trials=2, memory_size=1)

    assert result.success is True
    assert len(result.trials) == 2
    assert result.trials[0].feedback.success is False
    assert result.trials[0].reflection.startswith("I forgot")
    assert len(result.memory) == 1


# ---------------------------------------------------------------------------
# LATS: MCTS-guided search with grounded external feedback and verbal
# reflection on failed branches. with_structured_output is mocked with
# include_raw=True support, matching the real fix in lats.py.
# ---------------------------------------------------------------------------

class _StructuredMock:
    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema

    def invoke(self, messages, **kwargs):
        return self.owner.structured(self.schema)


class LATSLLM:
    def with_structured_output(self, schema, *, method, include_raw=False):
        assert method == "json_schema"
        assert include_raw is True  # the real fix: token usage requires this
        return _StructuredMock(self, schema)

    def structured(self, schema):
        parsed = self._parsed_for(schema)
        raw = SimpleNamespace(response_metadata={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}})
        return {"parsed": parsed, "raw": raw, "parsing_error": None}

    def _parsed_for(self, schema):
        if schema.__name__ == "LATSActionBatch":
            return schema.model_validate({
                "actions": [
                    {"action": "minimal", "course_ids": [2], "state": "course 2"},
                    {"action": "complete", "course_ids": [1, 2], "state": "course 1, course 2"},
                ]
            })
        return schema(score=0.8)

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(
            content="This branch is missing the course 1 prerequisite; add it before course 2.",
            response_metadata={"token_usage": {"prompt_tokens": 8, "completion_tokens": 4}},
        )


def test_lats_uses_external_feedback_reflection_and_backpropagation():
    catalog_data = fake_catalog_data()
    catalog_data["prerequisites"] = [{"course_id": 2, "prerequisite_course_id": 1}]
    environment = FakeEnvironment(catalog_data, feedback_sequence=[
        EnvironmentFeedback(success=False, score=0.2, details=["Course 2 requires course 1."]),
        EnvironmentFeedback(success=True, score=1.0, details=[]),
    ])

    result, metrics = lats(
        "Propose a course path covering python and sql",
        LATSLLM(),
        environment,
        iterations=1,
        n_actions=2,
    )

    assert result.success is True
    assert result.best_score == 1.0
    assert metrics["algorithm"] == "LATS"
    assert metrics["prompt_tokens"] > 0  # confirms the include_raw=True token fix is wired up
    assert "llm_calls" in metrics

    tree = flatten_lats_tree(result.root)
    assert len(tree) == 3
    assert tree[1]["feedback"]["success"] is False
    assert tree[2]["feedback"]["success"] is True


# ---------------------------------------------------------------------------
# Routing: each sub-task category should reach the algorithm whose shape
# genuinely fits it (see routing.py's keyword-based dispatch).
# ---------------------------------------------------------------------------

class RoutingLLM:
    """Minimal LLM stub covering both the plain .invoke() (Plan-and-Solve)
    and the .with_structured_output(..., include_raw=True) (ToT, LATS)
    paths route_and_execute_subtask can dispatch to."""

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(
            content="Plan: parse constraints. Solution: budget=500, weekly_hours=10.",
            response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 5}},
        )

    def with_structured_output(self, schema, *, method, include_raw=False):
        assert include_raw is True
        return _RoutingStructuredMock(schema)


class _RoutingStructuredMock:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages, **kwargs):
        raw = SimpleNamespace(response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 5}})
        if self.schema.__name__ == "ThoughtCandidates":
            parsed = self.schema(candidates=["course 1, course 2"])
        elif self.schema.__name__ == "ThoughtEvaluation":
            parsed = self.schema(score=0.8, rationale="Covers both required skills.")
        elif self.schema.__name__ == "LATSActionBatch":
            parsed = self.schema.model_validate({"actions": [{"action": "propose", "course_ids": [1, 2], "state": "course 1, course 2"}]})
        else:
            parsed = self.schema(score=0.8)
        return {"parsed": parsed, "raw": raw, "parsing_error": None}


@pytest.mark.parametrize(
    "category, description, expected_algo",
    [
        ("extract_parse", "Extract and parse this student's stated budget and weekly hours", "Plan-and-Solve"),
        ("rank_sequence", "Rank three possible course orderings for a Data Analyst target role", "Tree of Thoughts"),
        ("schedule_optimize", "Generate and validate the final optimized course schedule and check total cost against the budget limit", "LATS"),
    ],
)
def test_router_correctly_routes_subtasks(category, description, expected_algo):
    subtask = {"description": description, "category": category}
    llm = RoutingLLM()
    catalog_data = fake_catalog_data()
    environment = FakeEnvironment(catalog_data, feedback_sequence=[
        EnvironmentFeedback(success=True, score=1.0, details=[]),
    ])

    result, metrics = route_and_execute_subtask(subtask, llm, environment)

    assert metrics["routed_algorithm"] == expected_algo
    assert result is not None


# ---------------------------------------------------------------------------
# Schema binding sanity check: every structured-output schema used across
# the pipeline must actually bind to the real LangChain/Mistral client
# (no network call is made -- with_structured_output() alone doesn't invoke).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "schema",
    [GeneratedPlan, DynamicDecision, ThoughtCandidates, ThoughtEvaluation, LATSActionBatch, ValueEstimate],
)
def test_structured_schemas_bind_with_langchain_mistral(schema):
    chat = ChatMistralAI(api_key="test-key", model="test-model")
    runnable = chat.with_structured_output(schema, method="json_schema", include_raw=True)
    assert runnable is not None