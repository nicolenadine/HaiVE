from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ContextRequest(BaseModel):
    """Reviewer response asking to read a repo file before rendering a verdict.

    Distinct from ReviewAgentOutput (which forbids extra fields and enforces
    passed/uncertain exclusivity) so the two response shapes never collide.
    """

    action: Literal["request_file"]
    path: str
    reason: str
