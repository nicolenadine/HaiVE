from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from haive.models.config import Settings
from haive.models.state import CURRENT_SCHEMA_VERSION, ProjectState
from haive.models.task import TaskExecutionRecord


class StateStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.github_repo or "/" not in settings.github_repo:
            raise ValueError("StateStore requires GITHUB_REPO in 'owner/repo' format.")
        owner, _, repo = settings.github_repo.partition("/")
        self._state_dir = Path.home() / ".haive" / "state" / owner / repo
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, project_id: str) -> Path:
        return self._state_dir / f"project_{project_id}.json"

    def _lock_path(self, project_id: str) -> Path:
        return self._state_dir / f"project_{project_id}.lock"

    def load_or_init(self, project_id: str) -> ProjectState:
        path = self._state_path(project_id)
        with FileLock(self._lock_path(project_id)):
            if not path.exists():
                now = datetime.now(tz=timezone.utc)
                state = ProjectState(project_id=project_id, created_at=now, updated_at=now)
                self._write(state)
                return state
            text = path.read_text()
            raw = json.loads(text)
            version = raw.get("schema_version")
            if version != CURRENT_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Cannot load state file {path}: schema_version mismatch "
                    f"(expected '{CURRENT_SCHEMA_VERSION}', got '{version}'). "
                    "The file may need to be reset or migrated."
                )
            return ProjectState.model_validate_json(text)

    def save(self, state: ProjectState) -> None:
        with FileLock(self._lock_path(state.project_id)):
            self._write(state)

    def merge_task_record(
        self, project_id: str, task_id: str, record: TaskExecutionRecord
    ) -> None:
        with FileLock(self._lock_path(project_id)):
            path = self._state_path(project_id)
            state = ProjectState.model_validate_json(path.read_text())
            state.tasks[task_id] = record
            state.updated_at = datetime.now(tz=timezone.utc)
            self._write(state)

    def _write(self, state: ProjectState) -> None:
        path = self._state_path(state.project_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(state.model_dump_json(indent=2))
        tmp.rename(path)
