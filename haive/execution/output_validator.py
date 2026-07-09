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
        """Locates the model's JSON answer, tolerating prose before or after it.

        A model that reasons out loud before its final answer can leave
        incidental "{...}" earlier in the text — an f-string it's quoting, a
        dict literal it's describing — that brace-balances but isn't valid
        JSON. Trusting the first brace-balanced span (as a naive scan would)
        picks up that false positive instead of the real answer. Every
        candidate span is validated with json.loads before being accepted;
        a span that merely balances but doesn't parse is skipped in favor of
        the next one.

        Brace depth is tracked with awareness of JSON string literals (quote
        and backslash-escape state), not just raw character counts — a single
        stray '{' or '}' inside a string value (e.g. generated source code
        containing a dict literal, f-string, or set comprehension) would
        otherwise desynchronize a naive counter and cut the span short before
        the real closing brace, producing invalid JSON that fails every
        candidate even though the model's actual answer was well-formed.
        """
        text = raw.strip()

        candidates: list[str] = []

        # Markdown-fenced JSON, if present, is checked first — it's an
        # explicit signal of intent, not just an incidental brace pair.
        match = _FENCE_RE.search(text)
        if match:
            candidates.append(match.group(1).strip())

        search_from = 0
        while True:
            start = text.find("{", search_from)
            if start < 0:
                break
            depth = 0
            end = None
            in_string = False
            escape = False
            for i, ch in enumerate(text[start:], start):
                if escape:
                    escape = False
                    continue
                if ch == "\\" and in_string:
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                break
            candidates.append(text[start : end + 1])
            search_from = start + 1

        for candidate in candidates:
            try:
                json.loads(candidate)
                return candidate
            except (ValueError, TypeError):
                continue

        return None
