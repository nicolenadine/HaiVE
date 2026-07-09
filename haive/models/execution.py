from __future__ import annotations

from pydantic import BaseModel


class CommandResult(BaseModel):
    command:          list[str]
    cwd:              str
    exit_code:        int
    stdout:           str
    stderr:           str
    timed_out:        bool
    duration_seconds: float
