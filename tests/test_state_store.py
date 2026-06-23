import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haive.models.state import CURRENT_SCHEMA_VERSION, ProjectState
from haive.models.task import TaskExecutionRecord, VerdictSummary
from haive.persistence.state_store import StateStore


def _make_store(tmp_path: Path) -> StateStore:
    settings = MagicMock()
    settings.github_repo = "owner/repo"
    store = StateStore(settings)
    store._state_dir = tmp_path
    return store


def _make_record(task_id: str) -> TaskExecutionRecord:
    return TaskExecutionRecord(
        task_id=task_id,
        verdict=VerdictSummary(passed=True, reason="all checks passed"),
        total_attempts=1,
    )


# ---------------------------------------------------------------------------
# TestLoadOrInit
# ---------------------------------------------------------------------------

class TestLoadOrInit:
    def test_creates_new_file_when_none_exists(self, tmp_path):
        store = _make_store(tmp_path)
        state = store.load_or_init("7")

        assert state.project_id == "7"
        assert (tmp_path / "project_7.json").exists()
        loaded = ProjectState.model_validate_json((tmp_path / "project_7.json").read_text())
        assert loaded.project_id == "7"

    def test_schema_version_mismatch_raises_descriptive_error(self, tmp_path):
        state_file = tmp_path / "project_9.json"
        state_file.write_text(json.dumps({
            "schema_version": "0",
            "project_id": "9",
            "tasks": {},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }))
        store = _make_store(tmp_path)

        with pytest.raises(RuntimeError) as exc_info:
            store.load_or_init("9")

        msg = str(exc_info.value)
        assert "project_9.json" in msg
        assert CURRENT_SCHEMA_VERSION in msg
        assert "0" in msg


# ---------------------------------------------------------------------------
# TestSave
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_and_load_round_trips(self, tmp_path):
        store = _make_store(tmp_path)
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        state = ProjectState(
            project_id="3",
            created_at=now,
            updated_at=now,
            tasks={"42": _make_record("42")},
        )

        store.save(state)
        loaded = store.load_or_init("3")

        assert loaded == state


# ---------------------------------------------------------------------------
# TestMergeTaskRecord
# ---------------------------------------------------------------------------

class TestMergeTaskRecord:
    def test_creates_state_if_file_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.merge_task_record("5", "task-X", _make_record("task-X"))
        state = store.load_or_init("5")
        assert state.project_id == "5"
        assert "task-X" in state.tasks

    def test_concurrent_writes_produce_valid_state(self, tmp_path):
        store = _make_store(tmp_path)
        store.load_or_init("1")

        barrier = threading.Barrier(2)

        def write_a():
            barrier.wait()
            store.merge_task_record("1", "task-A", _make_record("task-A"))

        def write_b():
            barrier.wait()
            store.merge_task_record("1", "task-B", _make_record("task-B"))

        t1 = threading.Thread(target=write_a)
        t2 = threading.Thread(target=write_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        final = store.load_or_init("1")
        assert "task-A" in final.tasks
        assert "task-B" in final.tasks
