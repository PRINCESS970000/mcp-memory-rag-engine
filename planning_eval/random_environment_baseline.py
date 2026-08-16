"""
Baseline for the LATS grounded-vs-ungrounded comparison required by the
rubric: "An environment.py still returning the toolkit's randomized
default at submission time is an ungrounded system." This file keeps that
randomized baseline available ON PURPOSE, only for this one comparison --
it is never used anywhere else in the agent.

Matches Environment's exact public interface (get_catalog_data(),
evaluate(state)) so lats.py can run against either one unmodified.
"""

"""
Baseline for the LATS grounded-vs-ungrounded comparison required by the
rubric: "An environment.py still returning the toolkit's randomized
default at submission time is an ungrounded system." This file keeps that
randomized baseline available ON PURPOSE, only for this one comparison --
it is never used anywhere else in the agent.

Matches Environment's exact public interface (get_catalog_data(),
evaluate(state)) so lats.py can run against either one unmodified.
"""

import random

from planning.algorithms.environment import Environment
from planning.models import EnvironmentFeedback


class RandomEnvironment:
    """Same interface as Environment, but evaluate() ignores the proposed
    state entirely -- this is the toolkit's original behavior
    (`random.betavariate(5.0, 2.0)`), kept only as the "ungrounded" side
    of the comparison table."""

    def __init__(self, student_id: int, mcp_server_path: str | None = None, seed: int = 42):
        # Reuses the real Environment purely to fetch the real catalog
        # (so both sides of the comparison see the same data) -- only
        # evaluate() is replaced with randomness.
        self._real_env = Environment(student_id=student_id, mcp_server_path=mcp_server_path)
        self._rng = random.Random(seed)

    def get_catalog_data(self) -> dict:
        return self._real_env.get_catalog_data()

    def evaluate(self, state) -> EnvironmentFeedback:
        score = round(self._rng.betavariate(5.0, 2.0), 4)
        return EnvironmentFeedback(
            success=score >= 0.7,
            score=score,
            details=["RandomEnvironment: score is not based on the proposed state."],
        )