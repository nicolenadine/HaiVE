from dataclasses import dataclass


@dataclass
class Tier:
    models:         list[str]
    max_attempts:   int
    context_budget: int

    def __post_init__(self) -> None:
        if not self.models:
            raise ValueError("Tier must have at least one model.")
        if self.max_attempts < 1:
            raise ValueError("Tier.max_attempts must be >= 1.")
        if self.context_budget < 1:
            raise ValueError("Tier.context_budget must be >= 1.")
