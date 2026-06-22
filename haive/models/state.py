from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from haive.models.task import TaskExecutionRecord

CURRENT_SCHEMA_VERSION = "1"


class ProjectState(BaseModel):
    schema_version: str = CURRENT_SCHEMA_VERSION
    project_id:     str
    tasks:          dict[str, TaskExecutionRecord] = Field(default_factory=dict)
    created_at:     datetime
    updated_at:     datetime
    last_run_at:    datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def check_schema_version(cls, data: dict) -> dict:
        v = data.get("schema_version")
        if v is not None and v != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"State file schema version mismatch: "
                f"expected '{CURRENT_SCHEMA_VERSION}', got '{v}'. "
                "The state file may need to be reset or migrated."
            )
        return data
