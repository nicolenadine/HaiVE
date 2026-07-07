from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from haive.models.agent_output import (
    ApiIntegrationAgentOutput,
    CodeEditorOutput,
    CodeReviewerOutput,
    DatabaseAgentOutput,
    DocumentationWriterOutput,
    ScaffoldAgentOutput,
    SecurityReviewerOutput,
    TestGeneratorOutput,
)
from haive.models.enums import AgentRole


class OutputValidationError(Exception):
    """Raised when an agent's raw output cannot be parsed or validated."""

    def __init__(self, role: AgentRole, raw: str, reason: str) -> None:
        self.role = role
        self.raw = raw
        super().__init__(f"OutputValidationError [{role.value}]: {reason}\nRaw output:\n{raw}")


_SCHEMA_MAP: dict[AgentRole, type[BaseModel]] = {
    AgentRole.SCAFFOLD_AGENT:             ScaffoldAgentOutput,
    AgentRole.IMPLEMENTATION_AGENT:       CodeEditorOutput,
    AgentRole.CODE_EDITOR_AGENT:          CodeEditorOutput,
    AgentRole.REFACTORING_AGENT:          CodeEditorOutput,
    AgentRole.API_INTEGRATION_AGENT:      ApiIntegrationAgentOutput,
    AgentRole.DATABASE_AGENT:             DatabaseAgentOutput,
    AgentRole.TEST_GENERATOR_AGENT:       TestGeneratorOutput,
    AgentRole.CODE_REVIEWER_AGENT:        CodeReviewerOutput,
    AgentRole.SECURITY_REVIEWER_AGENT:    SecurityReviewerOutput,
    AgentRole.DOCUMENTATION_WRITER_AGENT: DocumentationWriterOutput,
}

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


class OutputValidator:
    """Validates raw LLM output against the schema for a given agent role."""

    def validate(self, raw: str, role: AgentRole) -> BaseModel:
        schema_class = _SCHEMA_MAP.get(role)
        if schema_class is None:
            raise OutputValidationError(role, raw, f"No schema registered for role '{role.value}'")

        json_str = self.extract_json(raw)
        if json_str is None:
            raise OutputValidationError(role, raw, "Could not locate a JSON object in the output")

        try:
            return schema_class.model_validate_json(json_str)
        except (ValidationError, ValueError) as e:
            raise OutputValidationError(role, raw, str(e)) from e

    @staticmethod
    def extract_json(raw: str) -> str | None:
        text = raw.strip()

        # Strategy 1: bare JSON object
        if text.startswith("{"):
            return text

        # Strategy 2: JSON inside a markdown fence
        match = _FENCE_RE.search(text)
        if match:
            return match.group(1).strip()

        # Strategy 3: brace scan for outermost { ... }
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1]

        return None
