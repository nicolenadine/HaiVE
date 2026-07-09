from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.execution import CommandResult

_MAX_ATTEMPT_LOG_REASON_CHARS = 50000
# TODO: temporarily generous (was 500) so failed schema-validation attempts
# keep their full raw output for diagnosis instead of being cut off after
# 500 chars, which made it impossible to tell truncated-by-max_tokens output
# apart from a parser bug after the fact. Restrict this again once there's
# a proper place (e.g. a per-task debug log) for the full text to live
# without bloating the orchestrator's prompt / GitHub comments.


class Project(BaseModel):
    project_id:     str
    title:          str
    description:    str
    project_branch: str
    checkpoint:     bool = True


class MilestoneSummary(BaseModel):
    number: int
    title:  str
    due_on: datetime | None = None


class Task(BaseModel):
    task_id:             str
    title:               str
    description:         str
    agent_role:          AgentRole
    complexity:          Complexity
    depends_on:          list[str]
    acceptance_criteria: list[str]
    status:              TaskStatus
    recovery_for:        str | None = None
    lineage_depth:       int = 0


class TaskComment(BaseModel):
    task_id:    str
    author:     str
    body:       str
    created_at: datetime


class AttemptLogEntry(BaseModel):
    tier:            Complexity
    attempt:         int
    reason:          str
    command_results: list[CommandResult] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def _truncate_reason(cls, v: str) -> str:
        """Bound at the source, since this reaches the orchestrator two ways:
        directly via TaskViewBuilder (record.attempt_log), and indirectly via
        a GitHub comment (_format_attempt_summary) read back as new_comments
        on a later run. An unbounded raw model output here (e.g. from a
        schema-validation failure) can bloat the orchestrator's prompt enough
        to break its own JSON output.
        """
        if len(v) <= _MAX_ATTEMPT_LOG_REASON_CHARS:
            return v
        return v[:_MAX_ATTEMPT_LOG_REASON_CHARS].rstrip() + "… [truncated]"


class VerdictSummary(BaseModel):
    passed: bool
    reason: str
    infeasible: bool = False


class TokenUsage(BaseModel):
    prompt_tokens:     int
    completion_tokens: int
    total_tokens:      int


class TaskExecutionRecord(BaseModel):
    task_id:        str
    verdict:        VerdictSummary | None = None
    attempt_log:    list[AttemptLogEntry] = Field(default_factory=list)
    model_used:     str | None = None
    tier_used:      Complexity | None = None
    total_attempts: int = 0
    prompt_version: str | None = None
    changed_files:  list[str] = Field(default_factory=list)
    pr_id:          str | None = None
    merged:         bool = True
    completed_at:   datetime | None = None
    token_usage:    TokenUsage | None = None
    executor_start: datetime | None = None
    executor_end:   datetime | None = None
