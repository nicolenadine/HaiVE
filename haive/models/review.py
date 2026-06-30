from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from haive.models.task import VerdictSummary


class ReviewVerdict(BaseModel):
    passed: bool
    reason: str
    suggestions: list[str] = Field(default_factory=list)
    uncertain: bool = False

    @model_validator(mode="after")
    def validate_consistency(self) -> "ReviewVerdict":
        if self.uncertain and self.passed:
            raise ValueError("uncertain=True and passed=True are mutually exclusive.")
        if not self.passed and not self.uncertain and not self.suggestions:
            raise ValueError("suggestions must be non-empty when passed=False and uncertain=False.")
        return self

    def to_summary(self) -> VerdictSummary:
        """Derive a stored VerdictSummary, dropping suggestions and uncertain."""
        return VerdictSummary(passed=self.passed, reason=self.reason)
