import subprocess
from pathlib import Path

import pytest

from haive.discovery.git_utils import get_changed_files


@pytest.fixture()
def git_repo(tmp_path):
    """Minimal git repo with one committed file."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "existing.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_modified_file_appears_in_changed(git_repo):
    (git_repo / "existing.py").write_text("x = 2\n")
    changed = get_changed_files(str(git_repo))
    assert "existing.py" in changed


def test_new_untracked_file_appears_in_changed(git_repo):
    (git_repo / "new_file.py").write_text("y = 1\n")
    changed = get_changed_files(str(git_repo))
    assert "new_file.py" in changed


def test_clean_repo_returns_empty(git_repo):
    assert get_changed_files(str(git_repo)) == []


def test_deleted_file_appears_in_changed(git_repo):
    (git_repo / "existing.py").unlink()
    changed = get_changed_files(str(git_repo))
    assert "existing.py" in changed


def test_nested_file_path_is_repo_relative(git_repo):
    subdir = git_repo / "pkg"
    subdir.mkdir()
    (subdir / "module.py").write_text("z = 1\n")
    changed = get_changed_files(str(git_repo))
    assert "pkg/module.py" in changed
