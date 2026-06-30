from __future__ import annotations

import subprocess


def get_changed_files(repo_root: str) -> list[str]:
    """Return repo-relative paths of files changed in the working tree vs HEAD.

    Combines:
    - git diff --name-only HEAD  (modified/deleted, staged or unstaged)
    - git status --porcelain     (newly created untracked files)
    """
    files: set[str] = set()

    # Tracked files: modified, deleted, or staged vs HEAD
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    files.update(p for p in diff.stdout.strip().splitlines() if p)

    # Untracked files not yet staged (new files the task agent created)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    files.update(p for p in untracked.stdout.strip().splitlines() if p)

    return sorted(files)
