from __future__ import annotations

import re
import tomllib
from pathlib import Path

from pydantic import BaseModel

_ALLOWLIST_RELATIVE_PATH = ".haive/allowed_dependencies.txt"
_MANIFEST_NAME = "pyproject.toml"
_NAME_SPLIT_RE = re.compile(r"[<>=!~\[; ]")


class DependencyApprovalResult(BaseModel):
    approved: bool
    unapproved_dependencies: list[str] = []
    warning: str = ""  # non-fatal notice (e.g. no allowlist configured for this project)


def _dependency_name(spec: str) -> str:
    """Extract the bare package name from a PEP 508 dependency spec.

    e.g. "requests>=2.0" -> "requests", "typer[all]==0.9" -> "typer".
    """
    return _NAME_SPLIT_RE.split(spec.strip(), maxsplit=1)[0].strip().lower()


def _dependency_names(pyproject_content: str) -> set[str]:
    try:
        data = tomllib.loads(pyproject_content)
    except tomllib.TOMLDecodeError:
        return set()
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group_specs in project.get("optional-dependencies", {}).values():
        specs.extend(group_specs)
    return {_dependency_name(dep) for dep in specs if _dependency_name(dep)}


def _load_allowlist(root: str) -> set[str] | None:
    """None means no allowlist file exists; the gate is inactive for this project."""
    path = Path(root, _ALLOWLIST_RELATIVE_PATH)
    if not path.is_file():
        return None
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped.lower())
    return names


class DependencyApprovalGate:
    """Blocks a brand-new, unapproved dependency from ever being installed.

    Dependencies expected by a project are declared up front, during planning
    and before haive starts executing tasks, in .haive/allowed_dependencies.txt
    (committed to the target repo). A dependency added mid-build that isn't on
    that list requires a human to explicitly approve it. Unlike every
    ExecutionVerifier stage, this is never retried: no amount of retrying lets
    an agent grant itself approval, so retrying would only waste attempts on a
    fix only a human can make. This check also runs before dependency_sync, so
    an unapproved package's install-time code never executes pending approval.
    """

    def __init__(self, root: str, enabled: bool = True) -> None:
        self._root = root
        self._enabled = enabled

    def check(
        self, changed_paths: list[str], original_contents: dict[str, str]
    ) -> DependencyApprovalResult:
        if not self._enabled or _MANIFEST_NAME not in changed_paths:
            return DependencyApprovalResult(approved=True)

        manifest_path = Path(self._root, _MANIFEST_NAME)
        if not manifest_path.is_file():
            return DependencyApprovalResult(approved=True)

        new_names = _dependency_names(manifest_path.read_text(encoding="utf-8"))
        old_content = original_contents.get(_MANIFEST_NAME, "")
        old_names = _dependency_names(old_content) if old_content else set()
        added = new_names - old_names
        if not added:
            return DependencyApprovalResult(approved=True)

        allowlist = _load_allowlist(self._root)
        if allowlist is None:
            return DependencyApprovalResult(
                approved=True,
                warning=(
                    f"No {_ALLOWLIST_RELATIVE_PATH} found — the dependency approval gate "
                    f"is inactive for this project. New dependency(ies) installed without "
                    f"human review: {', '.join(sorted(added))}. Add "
                    f"{_ALLOWLIST_RELATIVE_PATH} to enable this check."
                ),
            )

        unapproved = sorted(added - allowlist)
        if unapproved:
            return DependencyApprovalResult(approved=False, unapproved_dependencies=unapproved)
        return DependencyApprovalResult(approved=True)
