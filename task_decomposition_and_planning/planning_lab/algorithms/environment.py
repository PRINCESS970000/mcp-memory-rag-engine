"""
Grounded Environment for the Adaptive Learning Path Planning agent.

Replaces the toolkit's algorithms/environment.py, which returns a random
beta-distributed score and ignores the candidate entirely.

Interface note: algorithms/lats.py and algorithms/routing.py (Person 2's
files) already do `from .environment import Environment` and call
`environment.evaluate(child.state)` where `state` is a free-text string
the model generated describing a candidate path -- not a structured
object. This file matches that exact interface rather than introducing a
different one, so LATS/routing don't need to change.

Because `evaluate()` only receives a free-text state string (LATS has no
separate parameter for which student this is), the student_id is fixed at
construction time: one Environment instance is built per planning session
for one student, and both Reflexion and LATS reuse the same instance.
"""

import re
from datetime import date

from ..models import EnvironmentFeedback


class Environment:
    """Grounded evaluator: checks a proposed learning path against real
    BrightPeak data (courses, prerequisites, learning_goals) via the
    get_path_planning_data MCP tool. No LLM call, no randomness.

    Follows the same pattern agent/loop.py already uses for db_tool
    questions (`from server import get_student_profile`) -- the MCP tool
    functions are plain Python functions decorated with @mcp.tool(), so
    they're imported and called directly, no separate MCP client object.
    """

    def __init__(self, student_id: int, mcp_server_path: str | None = None):
        self.student_id = student_id
        if mcp_server_path:
            import sys
            sys.path.insert(0, mcp_server_path)
        self._data_cache: dict | None = None

    def get_catalog_data(self) -> dict:
        """Public accessor for this session's cached student/catalog data --
        the same dict reflexion() needs as its catalog_data argument, so
        callers don't have to reach into the private _fetch_data()."""
        return self._fetch_data()

    def _fetch_data(self) -> dict:
        # Cached per instance: within one planning session (one Reflexion
        # run or one LATS search) the student's catalog/goal don't change
        # between calls, so there's no need to re-query the DB every node.
        if self._data_cache is None:
            from server import get_path_planning_data
            result = get_path_planning_data(self.student_id)
            if result["status"] != "success":
                raise RuntimeError(f"get_path_planning_data failed: {result['message']}")
            self._data_cache = result["data"]
        return self._data_cache

    def evaluate(self, state: str | list[int]) -> EnvironmentFeedback:
        """state: either the free-text path description LATS/routing pass
        (course_ids are extracted from it, filtered against the real
        catalog so stray numbers -- prices, hours -- aren't mistaken for
        course ids), or a plain list[int] of course_ids (what
        reflexion.py in this same folder passes directly)."""
        data = self._fetch_data()
        courses_by_id = {c["course_id"]: c for c in data["courses"]}

        if isinstance(state, str):
            course_ids = self._extract_course_ids(state, valid_ids=set(courses_by_id))
        else:
            course_ids = list(state)

        issues: list[str] = []
        issues.extend(self._check_prerequisites(
            course_ids, data["prerequisites"], data["completed_course_ids"]
        ))

        goal = data["learning_goal"]
        if goal is None:
            return EnvironmentFeedback(
                success=False, score=0.0,
                details=["No learning_goal set for this student; cannot evaluate a path."],
            )

        path_courses = [courses_by_id[cid] for cid in course_ids if cid in courses_by_id]
        checks_passed = 1 if not issues else 0  # prerequisites result
        total_checks = 6

        # Budget
        total_price = sum(c["price"] for c in path_courses)
        if total_price > goal["budget"]:
            issues.append(f"Path costs {total_price:.2f}, exceeding the budget of {goal['budget']:.2f}.")
        else:
            checks_passed += 1

        # Weekly hours (date overlap)
        hours_ok = True
        for i, a in enumerate(path_courses):
            a_start, a_end = date.fromisoformat(a["start_date"]), date.fromisoformat(a["end_date"])
            overlapping_hours = a["weekly_hours"]
            for j, b in enumerate(path_courses):
                if i == j:
                    continue
                b_start, b_end = date.fromisoformat(b["start_date"]), date.fromisoformat(b["end_date"])
                if a_start <= b_end and b_start <= a_end:
                    overlapping_hours += b["weekly_hours"]
            if overlapping_hours > goal["weekly_hours_available"]:
                hours_ok = False
                issues.append(
                    f"Course {a['course_id']} ('{a['title']}') overlaps with others totalling "
                    f"{overlapping_hours} weekly hours, exceeding {goal['weekly_hours_available']} available."
                )
        if hours_ok:
            checks_passed += 1

        # Schedule ordering for dependent courses
        required_by_course: dict[int, list[int]] = {}
        for edge in data["prerequisites"]:
            required_by_course.setdefault(edge["course_id"], []).append(edge["prerequisite_course_id"])
        schedule_ok = True
        completed_ids = set(data["completed_course_ids"])
        path_ids = {c["course_id"] for c in path_courses}
        for course in path_courses:
            for prereq_id in required_by_course.get(course["course_id"], []):
                if prereq_id in completed_ids or prereq_id not in courses_by_id or prereq_id not in path_ids:
                    continue
                prereq = courses_by_id[prereq_id]
                if date.fromisoformat(prereq["end_date"]) > date.fromisoformat(course["start_date"]):
                    schedule_ok = False
                    issues.append(
                        f"Course {course['course_id']} starts {course['start_date']}, before its "
                        f"prerequisite {prereq_id} ends ({prereq['end_date']})."
                    )
        if schedule_ok:
            checks_passed += 1

        # Skill coverage
        covered_skills: set[str] = set()
        for c in path_courses:
            covered_skills.update(tag.strip() for tag in c["skill_tags"].split(","))
        missing_skills = set(data["required_skills"]) - covered_skills
        if missing_skills:
            issues.append(f"Path does not cover required skills: {', '.join(sorted(missing_skills))}.")
        else:
            checks_passed += 1

        # Deadline
        if path_courses:
            latest_end = max(date.fromisoformat(c["end_date"]) for c in path_courses)
            target_date = date.fromisoformat(goal["target_date"])
            if latest_end > target_date:
                issues.append(f"Path finishes {latest_end.isoformat()}, after target date {goal['target_date']}.")
            else:
                checks_passed += 1

        success = len(issues) == 0
        score = round(checks_passed / total_checks, 4)
        return EnvironmentFeedback(success=success, score=score, details=issues)

    def _extract_course_ids(self, text: str, valid_ids: set[int]) -> list[int]:
        """Pull course_ids out of a free-text model-generated description.

        Prefers explicit "course 14" / "course_id: 14" / "course #14"
        mentions -- this avoids the failure mode where an incidental
        number in the prose (a price, an hours-per-week figure, a date)
        happens to match a real course_id and gets mistaken for one, e.g.
        "...course 7, 6 hours/week..." should extract [7], not [7, 6].
        Only falls back to bare numbers filtered by valid_ids if no
        explicit "course N" mentions are found at all."""
        seen: set[int] = set()
        course_ids: list[int] = []

        explicit = re.findall(r"course\s*(?:id)?\s*[:#]?\s*(\d+)", text, re.IGNORECASE)
        for match in explicit:
            n = int(match)
            if n in valid_ids and n not in seen:
                course_ids.append(n)
                seen.add(n)
        if course_ids:
            return course_ids

        # Fallback: no explicit "course N" phrasing found at all, so take
        # any number that's a valid course_id. Less precise, but only
        # used when the preferred pattern matches nothing.
        for match in re.findall(r"\d+", text):
            n = int(match)
            if n in valid_ids and n not in seen:
                course_ids.append(n)
                seen.add(n)
        return course_ids

    def _check_prerequisites(
        self,
        course_ids: list[int],
        prerequisites: list[dict],
        completed_course_ids: list[int],
    ) -> list[str]:
        """Every course in the path must have its prerequisites either
        already completed, or scheduled earlier in the same path."""
        issues: list[str] = []
        completed = set(completed_course_ids)

        required_by_course: dict[int, list[int]] = {}
        for edge in prerequisites:
            required_by_course.setdefault(edge["course_id"], []).append(edge["prerequisite_course_id"])

        position = {cid: i for i, cid in enumerate(course_ids)}

        seen = set()
        for i, course_id in enumerate(course_ids):
            if course_id in seen:
                issues.append(f"Course {course_id} appears more than once in the path.")
            seen.add(course_id)

            for prereq_id in required_by_course.get(course_id, []):
                if prereq_id in completed:
                    continue
                prereq_position = position.get(prereq_id)
                if prereq_position is None:
                    issues.append(
                        f"Course {course_id} requires course {prereq_id}, "
                        f"which is neither completed nor included in the path."
                    )
                elif prereq_position >= i:
                    issues.append(
                        f"Course {course_id} requires course {prereq_id}, "
                        f"but {prereq_id} is scheduled at or after it in the path."
                    )
        return issues
