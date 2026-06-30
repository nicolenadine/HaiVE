from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from haive.execution.output_validator import OutputValidationError, OutputValidator
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.models.agent_output import ReviewAgentOutput
from haive.models.discovery import LoadedSection
from haive.models.enums import AgentRole
from haive.models.review import ReviewVerdict
from haive.models.task import Task

# Ordered least-capable to most-capable. The reviewer advances on uncertain.
REVIEWER_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
]

_REVIEW_MAX_TOKENS = 2048
_REVIEW_CONTEXT_BUDGET = 32_000


class ReviewAgent:
    """LLM-as-judge that evaluates task agent output against acceptance criteria.

    Advances through REVIEWER_MODELS (cheapest first) when uncertain.
    If all models return uncertain, returns a definitive passed=False verdict.
    """

    def __init__(
        self,
        model_client: ModelClient,
        system_prompt: str,
        guidelines: str,
    ) -> None:
        self._client = model_client
        self._system_prompt = system_prompt
        self._guidelines = guidelines
        self._validator = OutputValidator()

    def review(
        self,
        task: Task,
        agent_output: BaseModel,
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
        discovery_note: str,
    ) -> ReviewVerdict:
        prompt = self._build_prompt(task, agent_output, loaded_sections, discovery_status, discovery_note)

        for i, model in enumerate(REVIEWER_MODELS):
            tier = Tier(models=[model], max_attempts=1, context_budget=_REVIEW_CONTEXT_BUDGET)
            response = self._client.call(
                tier=tier,
                prompt=prompt,
                system=self._system_prompt,
                max_tokens=_REVIEW_MAX_TOKENS,
            )
            try:
                output = self._validator.validate(response.content, AgentRole.CODE_REVIEWER_AGENT)
                assert isinstance(output, ReviewAgentOutput)
            except (OutputValidationError, AssertionError):
                if i == len(REVIEWER_MODELS) - 1:
                    return ReviewVerdict(
                        passed=False,
                        reason="Reviewer failed to produce a valid output after all model attempts.",
                        suggestions=["Manual review required."],
                    )
                continue

            if not output.uncertain:
                return self._to_verdict(output)

        # All models returned uncertain — default to failed.
        return ReviewVerdict(
            passed=False,
            reason="All reviewer models returned uncertain — defaulting to failed.",
            suggestions=["Manual review required."],
        )

    # ── private helpers ───────────────────────────────────────────────────────

    def _build_prompt(
        self,
        task: Task,
        agent_output: BaseModel,
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
        discovery_note: str,
    ) -> str:
        parts: list[str] = []

        parts.append("## Task\n")
        parts.append(f"**{task.title}**\n\n{task.description.strip()}")
        if task.acceptance_criteria:
            parts.append("\n**Acceptance criteria:**")
            for ac in task.acceptance_criteria:
                parts.append(f"- {ac}")

        if loaded_sections:
            parts.append("\n## Code Context\n")
            for s in loaded_sections:
                parts.append(f"### {s.file}\n\n{s.reason}\n\n```\n{s.source.rstrip()}\n```")

        parts.append("\n## Agent Output\n")
        parts.append(f"```json\n{agent_output.model_dump_json(indent=2)}\n```")

        parts.append("\n## Guidelines\n")
        parts.append(self._guidelines.strip())

        if discovery_status == "empty_unexpected":
            parts.append(
                "\n## ⚠️ No Code Context Was Available\n"
                f"{discovery_note}\n\n"
                "The agent produced this output without access to any existing relevant code. "
                "Apply extra scrutiny: verify the output does not assume context it never received, "
                "and that it does not conflict with patterns or conventions in the codebase."
            )

        parts.append(
            '\n\nReturn your verdict as a JSON object:\n'
            '{"passed": bool, "uncertain": bool, "findings": [...], "summary": "..."}\n'
            "Set uncertain=true (and passed=false) only if you genuinely cannot determine "
            "correctness without additional context."
        )

        return "\n".join(parts)

    @staticmethod
    def _to_verdict(output: ReviewAgentOutput) -> ReviewVerdict:
        suggestions = [
            f.suggestion if f.suggestion else f.message
            for f in output.findings
        ]
        return ReviewVerdict(
            passed=output.passed,
            reason=output.summary,
            suggestions=suggestions,
            uncertain=output.uncertain,
        )
