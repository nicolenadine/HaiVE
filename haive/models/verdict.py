from pydantic import BaseModel


class ReviewVerdict(BaseModel):
    passed:      bool
    reason:      str
    suggestions: list[str]
    uncertain:   bool = False
