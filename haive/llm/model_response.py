from __future__ import annotations

from dataclasses import dataclass

from haive.models.task import TokenUsage


@dataclass
class ModelResponse:
    content:     str
    model_used:  str
    token_usage: TokenUsage | None = None
