from dataclasses import dataclass


@dataclass
class Tier:
    models:         list[str]
    max_attempts:   int
    context_budget: int

    def __post_init__(self) -> None:
        if not self.models:
            raise ValueError("Tier must have at least one model.")
