from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from haive.execution.output_validator import OutputValidationError, OutputValidator
from haive.execution.read_file_tool import run_tool_loop
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

# A review addressing several acceptance criteria with detailed findings
# (file, line, severity, message, suggestion per finding) can easily run past
# a couple thousand tokens — 2048 was found too tight in practice, causing
# the response to cut off mid-JSON and fail validation identically across
# every model in REVIEWER_MODELS, not just an occasional one. Matches the
# same class of fix already applied to test_generator_agent's max_tokens.
_REVIEW_MAX_TOKENS = 4096
_REVIEW_CONTEXT_BUDGET = 32_000

# Safety valve against non-progressing loops (e.g. repeatedly requesting an
# empty or nonexistent file, which consumes no token budget). Not a scope
# limit — the token budget is what bounds how much context can be pulled in.
_REVIEW_MAX_CONTEXT_ROUNDS = 20


class ReviewAgent:
    """LLM-as-judge that evaluates task agent output against acceptance criteria.

    Advances through REVIEWER_MODELS (cheapest first) when uncertain.
    If all models return uncertain, returns a definitive passed=False verdict.

    May read additional repo files on demand (via the shared read_file tool,
    haive/execution/read_file_tool.py) when it needs to verify a claim not
    covered by loaded_sections — bounded by a shared token budget across the
    whole review() call.
    """

    def __init__(
        self,
        model_client: ModelClient,
        system_prompt: str,
        guidelines: str,
        root: str,
    ) -> None:
        self._client = model_client
        self._system_prompt = system_prompt
        self._guidelines = guidelines
        self._root = root
        self._validator = OutputValidator()

    def review(
        self,
        task: Task,
        agent_output: BaseModel,
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
        discovery_note: str,
        original_contents: dict[str, str],
        execution_summary: str = "",
    ) -> ReviewVerdict:
        prompt = self._build_prompt(
            task, agent_output, loaded_sections, discovery_status, discovery_note,
            original_contents, execution_summary,
        )
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]
        remaining_budget = _REVIEW_CONTEXT_BUDGET

        for i, model in enumerate(REVIEWER_MODELS):
            tier = Tier(models=[model], max_attempts=1, context_budget=_REVIEW_CONTEXT_BUDGET)
            result = run_tool_loop(
                self._client, tier, messages, _REVIEW_MAX_TOKENS,
                self._root, remaining_budget, _REVIEW_MAX_CONTEXT_ROUNDS,
            )
            messages = result.messages
            remaining_budget = result.remaining_budget

            try:
                output = self._validator.validate(result.content, AgentRole.CODE_REVIEWER_AGENT)
                assert isinstance(output, ReviewAgentOutput)
            except (OutputValidationError, AssertionError):
                if i == len(REVIEWER_MODELS) - 1:
                    # Preserve an excerpt of the last (most capable) model's raw
                    # output — without this, a parse failure here is a total
                    # black box: the reason string is the only place any trace
                    # of what actually went wrong survives past this call.
                    excerpt = result.content[:500]
                    if len(result.content) > 500:
                        excerpt += "... [truncated]"
                    return ReviewVerdict(
                        passed=False,
                        reason=(
                            "Reviewer failed to produce a valid output after all model "
                            f"attempts. Last raw output: {excerpt}"
                        ),
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

    # ── prompt building ───────────────────────────────────────────────────────

    def _build_prompt(
        self,
        task: Task,
        agent_output: BaseModel,
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
        discovery_note: str,
        original_contents: dict[str, str],
        execution_summary: str,
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

        if original_contents:
            parts.append(
                "\n## Original File Content (full state before this task's own edits)\n"
            )
            for path, content in original_contents.items():
                parts.append(f"### {path}\n\n```\n{content.rstrip()}\n```")

        parts.append("\n## Agent Output\n")
        parts.append(f"```json\n{agent_output.model_dump_json(indent=2)}\n```")

        if execution_summary:
            parts.append("\n## Execution Verification\n")
            parts.append(
                "This submission was already applied to disk and passed cheap, deterministic "
                "checks (syntax, imports, and any configured project commands) before reaching "
                "you. Treat this as real, factual evidence — not a claim to re-verify from "
                f"reading code alone:\n\n{execution_summary}"
            )

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
            "correctness without additional context.\n\n"
            "If you need to verify a specific behavioral or architectural claim that isn't covered "
            "by the Code Context above — for example, confirming what a referenced function or "
            "callback actually receives — use the read_file tool to read that file before answering. "
            "Only request files you can identify from imports or references already visible above."
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
            infeasible=output.infeasible,
        )
