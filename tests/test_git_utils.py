from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from haive.discovery.git_utils import get_changed_files
from haive.models.execution import CommandResult


def _result(stdout: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(
        command=["git"], cwd=".", exit_code=exit_code, stdout=stdout, stderr="",
        timed_out=False, duration_seconds=0.01,
    )


def _mock_runner(diff_stdout: str = "", status_stdout: str = "", exit_code: int = 0) -> MagicMock:
    runner = MagicMock()

    def _run(command, **kwargs):
        if "diff" in command:
            return _result(diff_stdout, exit_code)
        return _result(status_stdout, exit_code)

    runner.run.side_effect = _run
    return runner


class TestGetChangedFiles:
    def test_returns_paths_from_diff(self, tmp_path):
        runner = _mock_runner(diff_stdout="a.py\nb.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert result == ["a.py", "b.py"]

    def test_returns_paths_from_status(self, tmp_path):
        runner = _mock_runner(status_stdout=" M c.py\n?? d.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert result == ["c.py", "d.py"]

    def test_deduplicates_across_commands(self, tmp_path):
        runner = _mock_runner(diff_stdout="a.py\n", status_stdout=" M a.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert result == ["a.py"]

    def test_handles_rename_in_status(self, tmp_path):
        runner = _mock_runner(status_stdout="R  old.py -> new.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert "new.py" in result
        assert "old.py" not in result

    def test_skips_fully_deleted_files(self, tmp_path):
        runner = _mock_runner(status_stdout="DD gone.py\n M kept.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert "gone.py" not in result
        assert "kept.py" in result

    def test_new_file_inside_new_directory_is_listed_individually(self, tmp_path):
        # Regression test: `git status --porcelain` without
        # --untracked-files=all collapses a whole new directory into one
        # line ("?? pkg/") instead of listing files inside it — this
        # actually broke a real test against a real git repo during
        # development, since a scaffolded file inside a not-yet-existing
        # package directory would otherwise vanish from changed_files.
        runner = _mock_runner(status_stdout="?? pkg/module.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert result == ["pkg/module.py"]

    def test_raises_on_git_diff_error(self, tmp_path):
        runner = _mock_runner(exit_code=128)
        with pytest.raises(RuntimeError, match="git diff failed"):
            get_changed_files(str(tmp_path), runner=runner)

    def test_returns_sorted_list(self, tmp_path):
        runner = _mock_runner(diff_stdout="z.py\na.py\nm.py\n")
        result = get_changed_files(str(tmp_path), runner=runner)
        assert result == sorted(result)
