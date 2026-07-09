from __future__ import annotations

from haive.execution.command_runner import CommandRunner

_GIT_TIMEOUT_SECONDS = 30


def get_changed_files(repo_root: str, runner: CommandRunner | None = None) -> list[str]:
    """Git-grounded list of files changed in the working tree.

    Uses `git diff --name-only HEAD` (tracked, modified files) and
    `git status --porcelain` (new/renamed/deleted files) — not agent
    self-reporting. An agent can crash, misreport, or touch more files than
    it declared; git does not.
    """
    runner = runner or CommandRunner()

    diff_result = runner.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=repo_root, timeout_seconds=_GIT_TIMEOUT_SECONDS
    )
    if diff_result.exit_code != 0:
        raise RuntimeError(f"git diff failed: {diff_result.stderr.strip()}")

    # --untracked-files=all: without it, git collapses an entire new
    # directory into one line (e.g. "?? haive/" instead of "?? haive/client.py")
    # when every file in it is untracked — exactly what a scaffold or a new
    # file under a not-yet-existing package directory produces.
    status_result = runner.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root, timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if status_result.exit_code != 0:
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
