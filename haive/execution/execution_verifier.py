from __future__ import annotations

import ast
import shlex
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from haive.discovery.path_safety import resolve_within_root
from haive.execution.command_runner import CommandRunner
from haive.models.enums import AgentRole
from haive.models.execution import CommandResult


class ExecutionCheckResult(BaseModel):
    passed:  bool
    stage:   Literal["path_safety", "dependency_sync", "syntax", "import", "command"] | None
    summary: str    # embedded in the reviewer's prompt as grounding when passed
    detail:  str    # used as retry_feedback when failed
    results: list[CommandResult] = []


_DEPENDENCY_MANIFEST_NAMES = {"pyproject.toml", "uv.lock"}


def _module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    rel = path[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    if not rel:
        return None
    return rel.replace("/", ".").replace("\\", ".")


class ExecutionVerifier:
    """Cheap, deterministic checks run before the LLM reviewer is called.

    A submission that fails here is rejected for free — no reviewer call is
    spent — with the concrete error fed back as retry feedback. Verification
    commands (stage 4) come only from *verification_commands*, supplied by
    the caller from configuration; this class never lets an LLM choose what
    to run.
    """

    def __init__(
        self,
        command_runner: CommandRunner,
        root: str,
        verification_commands: list[str],
        skip_roles: list[AgentRole],
        import_timeout_seconds: int,
        command_timeout_seconds: int,
        setup_command: str = "",
        setup_timeout_seconds: int = 180,
        enabled: bool = True,
    ) -> None:
        self._runner = command_runner
        self._root = root
        self._skip_roles = set(skip_roles)
        self._import_timeout = import_timeout_seconds
        self._command_timeout = command_timeout_seconds
        self._setup_timeout = setup_timeout_seconds
        self._enabled = enabled
        self._commands = verification_commands or self._auto_detect_commands()
        self._setup_command = setup_command or self._auto_detect_setup_command()

    def _auto_detect_commands(self) -> list[str]:
        if Path(self._root, "tests").is_dir():
            # Bare "python" is not guaranteed to exist on PATH (e.g. macOS
            # with only "python3", or no ambient interpreter at all) — this
            # crashed for real (FileNotFoundError: 'python') the first time
            # it ran against a project without one. Use the same resolved
            # interpreter as the import check, not an unresolved literal.
            return [f"{self._resolve_python()} -m pytest -q"]
        return []

    def _auto_detect_setup_command(self) -> str:
        if Path(self._root, "pyproject.toml").is_file():
            # Bare "uv sync" only installs the base [project.dependencies]
            # group -- it actively *uninstalls* anything declared under
            # [project.optional-dependencies] (e.g. a "dev" group holding
            # pytest) that happened to already be present, since it
            # reconciles .venv to match only the default group. This crashed
            # for real: every attempt's auto-detected "pytest -q" check
            # failed with "No module named pytest" after the very first
            # "uv sync" call uninstalled it. --all-extras installs every
            # declared optional group, never leaving test/dev tooling out.
            return "uv sync --all-extras"
        return ""

    def _resolve_python(self) -> str:
        venv_python = Path(self._root, ".venv", "bin", "python")
        if venv_python.is_file():
            return str(venv_python)
        return sys.executable

    def _venv_missing(self) -> bool:
        return not Path(self._root, ".venv", "bin", "python").is_file()

    def verify(self, changed_paths: list[str], agent_role: AgentRole) -> ExecutionCheckResult:
        if not self._enabled:
            return ExecutionCheckResult(
                passed=True, stage=None,
                summary="Execution verification is disabled for this project.", detail="",
            )

        results: list[CommandResult] = []

        for path_str in changed_paths:
            if resolve_within_root(path_str, self._root) is None:
                return ExecutionCheckResult(
                    passed=False,
                    stage="path_safety",
                    summary="",
                    detail=f"Path escapes the project root and was rejected: {path_str!r}",
                    results=results,
                )

        manifest_changed = any(p in _DEPENDENCY_MANIFEST_NAMES for p in changed_paths)
        if self._setup_command and (manifest_changed or self._venv_missing()):
            command = shlex.split(self._setup_command)
            result = self._runner.run(command, cwd=self._root, timeout_seconds=self._setup_timeout)
            results.append(result)
            if not result.timed_out and result.exit_code != 0:
                return ExecutionCheckResult(
                    passed=False,
                    stage="dependency_sync",
                    summary="",
                    detail=(
                        f"Dependency sync command failed: {self._setup_command}\n"
                        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                    ),
                    results=results,
                )

        py_paths = [p for p in changed_paths if p.endswith(".py")]
        if not py_paths:
            return ExecutionCheckResult(
                passed=True,
                stage=None,
                summary="No Python files changed — execution checks skipped.",
                detail="",
                results=results,
            )

        for path_str in py_paths:
            full = Path(self._root, path_str)
            try:
                ast.parse(full.read_text(encoding="utf-8"), filename=path_str)
            except SyntaxError as exc:
                return ExecutionCheckResult(
                    passed=False,
                    stage="syntax",
                    summary="",
                    detail=f"Syntax error in {path_str}: {exc}",
                    results=results,
                )

        modules = sorted({m for m in (_module_name(p) for p in py_paths) if m})
        if modules:
            python = self._resolve_python()
            import_code = "; ".join(f"import {m}" for m in modules)
            result = self._runner.run(
                [python, "-c", import_code], cwd=self._root, timeout_seconds=self._import_timeout
            )
            results.append(result)
            if not result.timed_out and result.exit_code != 0:
                return ExecutionCheckResult(
                    passed=False,
                    stage="import",
                    summary="",
                    detail=f"Import check failed:\n{result.stderr or result.stdout}",
                    results=results,
                )

        if agent_role not in self._skip_roles:
            for command_str in self._commands:
                command = shlex.split(command_str)
                result = self._runner.run(command, cwd=self._root, timeout_seconds=self._command_timeout)
                results.append(result)
                if result.timed_out:
                    continue  # inconclusive — a slow-but-correct suite isn't broken code
                if result.exit_code != 0:
                    return ExecutionCheckResult(
                        passed=False,
                        stage="command",
                        summary="",
                        detail=(
                            f"Verification command failed: {command_str}\n"
                            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                        ),
                        results=results,
                    )

        return ExecutionCheckResult(
            passed=True,
            stage=None,
            summary=self._build_summary(results),
            detail="",
            results=results,
        )

    @staticmethod
    def _build_summary(results: list[CommandResult]) -> str:
        parts = ["Syntax: OK.", "Imports: OK." if results else "Imports: nothing to check."]
        for r in results:
            cmd_str = " ".join(r.command)
            if r.timed_out:
                parts.append(f"`{cmd_str}`: timed out after {r.duration_seconds:.0f}s (inconclusive).")
                continue
            tail_lines = r.stdout.strip().splitlines()
            tail = tail_lines[-1] if tail_lines else ""
            parts.append(f"`{cmd_str}`: exit {r.exit_code}. {tail}".strip())
        return " ".join(parts)
