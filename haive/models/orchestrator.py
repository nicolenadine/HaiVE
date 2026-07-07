from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import AttemptLogEntry, Project, TaskComment, VerdictSummary


class OrchestratorTaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id:       str
    title:         str
    description:   str
    agent_role:    AgentRole
    complexity:    Complexity
    depends_on:    list[str]
    lineage_depth: int
    recovery_for:  str | None
    status:        TaskStatus
    verdict:       VerdictSummary | None
    attempt_log:   list[AttemptLogEntry]


class OrchestratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project:       Project
    tasks:         list[OrchestratorTaskView]
    new_comments:  list[TaskComment]
    agent_summary: str
    repo_map:      str = ""


class NewTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title:               str
    description:         str
    agent_role:          AgentRole
    complexity:          Complexity
    depends_on:          list[str] = Field(default_factory=list)
    acceptance_criteria: list[str]
    recovery_for:        str | None = None
    lineage_depth:       int = 0


class OrchestratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_tasks: list[NewTask] = Field(default_factory=list)
    done:      bool = False

    @model_validator(mode="after")
    def done_requires_empty_tasks(self) -> "OrchestratorOutput":
        if self.done and self.new_tasks:
            raise ValueError("done=True requires new_tasks to be empty")
        return self
