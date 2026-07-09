import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.state import ProjectState
from haive.models.task import (
    AttemptLogEntry,
    TaskExecutionRecord,
    VerdictSummary,
)
from haive.models.verdict import ReviewVerdict


def _make_record(task_id: str, passed: bool = True) -> TaskExecutionRecord:
    return TaskExecutionRecord(
        task_id=task_id,
        verdict=VerdictSummary(passed=passed, reason="looks good"),
        attempt_log=[
            AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="first try"),
        ],
        tier_used=Complexity.MEDIUM,
        total_attempts=1,
        changed_files=["src/foo.py"],
        pr_id="42",
        completed_at=datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc),
        token_usage=None,
    )


def _make_state(n: int = 5) -> ProjectState:
    now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
    tasks = {str(i): _make_record(str(i)) for i in range(1, n + 1)}
    return ProjectState(
        project_id="7",
        tasks=tasks,
        created_at=now,
        updated_at=now,
    )


class TestProjectStateRoundTrip:
    def test_serializes_to_valid_json(self):
        state = _make_state(5)
        raw = state.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["project_id"] == "7"
        assert len(parsed["tasks"]) == 5

    def test_deserializes_equal_to_original(self):
        state = _make_state(5)
        raw = state.model_dump_json()
        restored = ProjectState.model_validate_json(raw)
        assert restored == state

    def test_tasks_keyed_by_task_id(self):
        state = _make_state(5)
        for key in state.tasks:
            assert state.tasks[key].task_id == key


class TestSchemaVersionMismatch:
    def test_mismatched_version_raises_validation_error(self):
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        data = {
            "schema_version": "99",
            "project_id": "7",
            "tasks": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        with pytest.raises(ValidationError) as exc_info:
            ProjectState.model_validate(data)
        msg = str(exc_info.value)
        assert "99" in msg
        assert "1" in msg
        assert "mismatch" in msg.lower()

    def test_matching_version_loads_cleanly(self):
        state = _make_state(1)
        raw = json.loads(state.model_dump_json())
        assert raw["schema_version"] == "1"
        restored = ProjectState.model_validate(raw)
        assert restored.schema_version == "1"


class TestAttemptLogEntryReasonTruncation:
    def test_short_reason_is_unchanged(self):
        entry = AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="short reason")
        assert entry.reason == "short reason"

    def test_long_reason_is_truncated(self):
        from haive.models.task import _MAX_ATTEMPT_LOG_REASON_CHARS
        over_limit = _MAX_ATTEMPT_LOG_REASON_CHARS + 1000
        entry = AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="x" * over_limit)
        assert len(entry.reason) < over_limit
        assert entry.reason.endswith("[truncated]")

    def test_truncation_boundary_is_exact(self):
        from haive.models.task import _MAX_ATTEMPT_LOG_REASON_CHARS
        entry = AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="x" * _MAX_ATTEMPT_LOG_REASON_CHARS)
        assert entry.reason == "x" * _MAX_ATTEMPT_LOG_REASON_CHARS  # exactly at the limit, untouched

        entry_over = AttemptLogEntry(
            tier=Complexity.MEDIUM, attempt=1, reason="x" * (_MAX_ATTEMPT_LOG_REASON_CHARS + 1)
        )
        assert entry_over.reason != "x" * (_MAX_ATTEMPT_LOG_REASON_CHARS + 1)


class TestSchemaConstraints:
    def test_attempt_log_entry_has_no_suggestions_field(self):
        fields = AttemptLogEntry.model_fields
        assert "suggestions" not in fields

    def test_verdict_summary_has_no_suggestions_field(self):
        fields = VerdictSummary.model_fields
        assert "suggestions" not in fields

    def test_review_verdict_has_suggestions_field(self):
        fields = ReviewVerdict.model_fields
        assert "suggestions" in fields

    def test_project_state_has_no_task_content_fields(self):
        fields = ProjectState.model_fields
        for forbidden in ("description", "title", "acceptance_criteria"):
            assert forbidden not in fields

    def test_review_verdict_uncertain_and_passed_can_coexist_at_schema_level(self):
        # Mutual exclusion is enforced by the executor, not the schema
        v = ReviewVerdict(passed=True, reason="ok", suggestions=[], uncertain=True)
        assert v.passed is True
        assert v.uncertain is True
