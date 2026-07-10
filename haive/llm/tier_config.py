from __future__ import annotations

from dataclasses import dataclass

from haive.llm.tier import Tier
from haive.models.config import Settings
from haive.models.enums import Complexity

_ORCHESTRATOR_CONTEXT_BUDGET = 32000


@dataclass
class TierConfig:
    low:          Tier
    medium:       Tier
    high:         Tier
    orchestrator: Tier

    @classmethod
    def from_settings(cls, settings: Settings) -> "TierConfig":
        return cls(
            low=Tier(
                models=settings.tier_low_models,
                max_attempts=settings.tier_low_max_attempts,
                context_budget=settings.tier_low_context_budget,
            ),
            medium=Tier(
                models=settings.tier_medium_models,
                max_attempts=settings.tier_medium_max_attempts,
                context_budget=settings.tier_medium_context_budget,
            ),
            high=Tier(
                models=settings.tier_high_models,
                max_attempts=settings.tier_high_max_attempts,
                context_budget=settings.tier_high_context_budget,
            ),
            orchestrator=Tier(
                models=settings.tier_high_models,
                max_attempts=1,
                context_budget=_ORCHESTRATOR_CONTEXT_BUDGET,
            ),
        )

    def for_complexity(self, complexity: Complexity) -> Tier:
        if complexity == Complexity.LOW:
            return self.low
        if complexity == Complexity.MEDIUM:
            return self.medium
        if complexity == Complexity.HIGH:
            return self.high
        raise ValueError(f"Unknown complexity value: {complexity!r}")
