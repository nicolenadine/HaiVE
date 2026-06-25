from __future__ import annotations

import subprocess


def get_changed_files(repo_root: str) -> list[str]:
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if diff_result.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff_result.stderr.strip()}")

    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if status_result.returncode != 0:
        raise RuntimeError(f"git status failed: {status_result.stderr.strip()}")

    paths: set[str] = set()

    for line in diff_result.stdout.splitlines():
        line = line.strip()
        if line:
            paths.add(line)

    for line in status_result.stdout.splitlines():
        if len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        if xy[0] == "D" and xy[1] == "D":
            continue
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path.strip())

    return sorted(paths)
