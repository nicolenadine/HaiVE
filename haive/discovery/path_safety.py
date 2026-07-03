from __future__ import annotations

from pathlib import Path


def resolve_within_root(relative: str, root: str) -> Path | None:
    """Return the resolved path only if it stays inside root; None otherwise."""
    root_resolved = Path(root).resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
        return candidate
    except ValueError:
        return None
