from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ── Scaffold Agent ────────────────────────────────────────────────────────────

class FileToCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Repo-relative path for the new file.")
    content: str = Field(description="Full content to write.")


class ScaffoldAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[FileToCreate] = Field(min_length=1, description="Files to create.")
    notes: str = Field(default="", description="Optional notes for the reviewer.")


# ── Code Editor (shared by implementation, refactoring, api integration, database) ──

class FileEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Repo-relative path of the file to edit.")
    content: str = Field(description="Complete new content for the file.")


class CodeEditorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: list[FileEdit] = Field(min_length=1, description="Files to write or overwrite.")
    notes: str = Field(default="", description="Optional notes for the reviewer.")


# ── Review Agent (code and security reviewer) ─────────────────────────────────

class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="Repo-relative path of the file containing the finding.")
    line: int | None = Field(default=None, description="1-based line number, if applicable.")
    severity: str = Field(description="One of: critical, major, minor, nitpick.")
    message: str = Field(description="Description of the finding.")
    suggestion: str = Field(default="", description="Suggested fix or improvement.")


class ReviewAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(description="True if the submission meets the acceptance criteria.")
    uncertain: bool = Field(
        default=False,
        description="True when the reviewer cannot determine correctness. Mutually exclusive with passed=True.",
    )
    infeasible: bool = Field(
        default=False,
        description=(
            "True when the acceptance criteria are architecturally unsatisfiable given the "
            "real code — not an implementation mistake. Mutually exclusive with passed=True "
            "and uncertain=True."
        ),
    )
    findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="Issues found. Empty when passed=True.",
    )
    summary: str = Field(description="One-paragraph summary of the review.")

    @model_validator(mode="after")
    def uncertain_and_passed_are_exclusive(self) -> "ReviewAgentOutput":
        if self.uncertain and self.passed:
            raise ValueError("uncertain=True and passed=True are mutually exclusive.")
        if self.infeasible and self.passed:
            raise ValueError("infeasible=True and passed=True are mutually exclusive.")
        if self.infeasible and self.uncertain:
            raise ValueError("infeasible=True and uncertain=True are mutually exclusive.")
        return self


# ── Test Generator ────────────────────────────────────────────────────────────

class TestGeneratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: list[FileEdit] = Field(min_length=1, description="Test files to write or overwrite.")
    notes: str = Field(default="", description="Optional notes about test coverage.")


# ── Documentation Writer ──────────────────────────────────────────────────────

class DocumentationWriterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: list[FileEdit] = Field(min_length=1, description="Documentation files to write or overwrite.")
    notes: str = Field(default="", description="Optional notes for the reviewer.")


# ── Stubs (same shape as CodeEditorOutput) ───────────────────────────────────

class ApiIntegrationAgentOutput(CodeEditorOutput):
    pass


class DatabaseAgentOutput(CodeEditorOutput):
    pass


class CodeReviewerOutput(ReviewAgentOutput):
    pass


class SecurityReviewerOutput(ReviewAgentOutput):
    pass
