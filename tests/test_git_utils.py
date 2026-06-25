from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from haive.repomap.git_utils import get_changed_files


def _mock_run(diff_stdout: str = "", status_stdout: str = "", returncode: int = 0):
    def _side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = returncode
        result.stderr = "fatal: not a git repository" if returncode != 0 else ""
        if "diff" in cmd:
            result.stdout = diff_stdout
        else:
            result.stdout = status_stdout
        return result
    return _side_effect


class TestGetChangedFiles:
    def test_returns_paths_from_diff(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="a.py\nb.py\n",
            status_stdout="",
        )):
            result = get_changed_files(str(tmp_path))
        assert result == ["a.py", "b.py"]

    def test_returns_paths_from_status(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="",
            status_stdout=" M c.py\n?? d.py\n",
        )):
            result = get_changed_files(str(tmp_path))
        assert result == ["c.py", "d.py"]

    def test_deduplicates_across_commands(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="a.py\n",
            status_stdout=" M a.py\n",
        )):
            result = get_changed_files(str(tmp_path))
        assert result == ["a.py"]
        assert len(result) == 1

    def test_handles_rename_in_status(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="",
            status_stdout="R  old.py -> new.py\n",
        )):
            result = get_changed_files(str(tmp_path))
        assert "new.py" in result
        assert "old.py" not in result

    def test_skips_fully_deleted_files(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="",
            status_stdout="DD gone.py\n M kept.py\n",
        )):
            result = get_changed_files(str(tmp_path))
        assert "gone.py" not in result
        assert "kept.py" in result

    def test_raises_on_git_diff_error(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(returncode=128)):
            with pytest.raises(RuntimeError, match="git diff failed"):
                get_changed_files(str(tmp_path))

    def test_returns_sorted_list(self, tmp_path):
        with patch("haive.repomap.git_utils.subprocess.run", side_effect=_mock_run(
            diff_stdout="z.py\na.py\nm.py\n",
            status_stdout="",
        )):
            result = get_changed_files(str(tmp_path))
        assert result == sorted(result)
