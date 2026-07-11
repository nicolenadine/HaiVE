from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from haive.models.enums import AgentRole

_SCAFFOLD_ROLES: frozenset[AgentRole] = frozenset({AgentRole.SCAFFOLD_AGENT})


class DiscoveredSection(BaseModel):
    file: str              # full repo-relative path, e.g. "haive/models/task.py"
    symbol: str | None     # symbol name if narrowed to one symbol, else None
    start_line: int | None # 1-based; None when full=True
    end_line: int | None
    full: bool             # True = load entire file; False = symbol/line range only
    reason: str            # one-sentence explanation of relevance


class DiscoveryResult(BaseModel):
    sections: list[DiscoveredSection]
    status: Literal["found", "empty"]


class LoadedSection(BaseModel):
    file: str    # full repo-relative path
    source: str  # loaded file content or line-range slice
    reason: str  # carried through from DiscoveredSection


def classify_discovery_status(
    result: DiscoveryResult, role: AgentRole
) -> Literal["found", "empty_expected", "empty_unexpected"]:
    """Classify a discovery result relative to what's normal for *role*.

    A scaffold task creates brand-new files, so finding nothing existing is
    expected; any other role finding nothing is unusual enough to flag,
    both to the generating agent (via a prompt note) and to
    CodeDiscoveryAgent itself (as a signal worth escalating to a stronger
    model before trusting the result).
    """
    if result.sections:
        return "found"
    if role in _SCAFFOLD_ROLES:
        return "empty_expected"
    return "empty_unexpected"
