from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


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
