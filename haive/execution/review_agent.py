from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationError

from haive.discovery.path_safety import resolve_within_root
from haive.execution.output_validator import OutputValidationError, OutputValidator
from haive.llm.model_client import ModelClient
from haive.llm.model_response import ModelResponse
from haive.llm.tier import Tier
from haive.llm.token_counter import TokenCounter
from haive.models.agent_output import ReviewAgentOutput
from haive.models.context_request import ContextRequest
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

# Safety valve against non-progressing loops (e.g. repeatedly requesting an
# empty or nonexistent file, which consumes no token budget). Not a scope
# limit — the token budget is what bounds how much context can be pulled in.
_REVIEW_MAX_CONTEXT_ROUNDS = 20


class ReviewAgent:
    """LLM-as-judge that evaluates task agent output against acceptance criteria.

    Advances through REVIEWER_MODELS (cheapest first) when uncertain.
    If all models return uncertain, returns a definitive passed=False verdict.

    May read additional repo files on demand (via a ContextRequest response)
    when it needs to verify a claim not covered by loaded_sections — bounded
    by a shared token budget across the whole review() call.
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
    ) -> ReviewVerdict:
        prompt = self._build_prompt(task, agent_output, loaded_sections, discovery_status, discovery_note)
        remaining_budget = _REVIEW_CONTEXT_BUDGET

        for i, model in enumerate(REVIEWER_MODELS):
            tier = Tier(models=[model], max_attempts=1, context_budget=_REVIEW_CONTEXT_BUDGET)
            response, prompt, remaining_budget = self._call_with_context_requests(
                tier, prompt, remaining_budget
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

    # ── context-request loop ──────────────────────────────────────────────────

    def _call_with_context_requests(
        self, tier: Tier, prompt: str, remaining_budget: int,
    ) -> tuple[ModelResponse, str, int]:
        """Calls the model, honoring ContextRequest responses until it returns
        a verdict, the budget runs out, or the round safety valve is hit.
        """
        for _ in range(_REVIEW_MAX_CONTEXT_ROUNDS):
            response = self._client.call(
                tier=tier, prompt=prompt, system=self._system_prompt, max_tokens=_REVIEW_MAX_TOKENS,
            )
            request = self._try_parse_context_request(response.content)
            if request is None:
                return response, prompt, remaining_budget

            if remaining_budget <= 0:
                prompt = (
                    f"{prompt}\n\n## Context budget exhausted\n"
                    "You must return a verdict now — no more files can be read."
                )
                response = self._client.call(
                    tier=tier, prompt=prompt, system=self._system_prompt, max_tokens=_REVIEW_MAX_TOKENS,
                )
                return response, prompt, remaining_budget

            content_block, tokens_used = self._read_requested_file(request.path, remaining_budget)
            prompt = (
                f"{prompt}\n\n## Additional Context Requested: {request.path}\n"
                f"Reason given: {request.reason}\n\n```\n{content_block}\n```"
            )
            remaining_budget -= tokens_used

        prompt = f"{prompt}\n\n## Context request limit reached\nYou must return a verdict now."
        response = self._client.call(
            tier=tier, prompt=prompt, system=self._system_prompt, max_tokens=_REVIEW_MAX_TOKENS,
        )
        return response, prompt, remaining_budget

    @staticmethod
    def _try_parse_context_request(raw: str) -> ContextRequest | None:
        json_str = OutputValidator.extract_json(raw)
        if json_str is None:
            return None
        try:
            return ContextRequest.model_validate_json(json_str)
        except (ValidationError, ValueError):
            return None

    def _read_requested_file(self, path: str, remaining_budget: int) -> tuple[str, int]:
        """Returns (content or error text to show the reviewer, tokens consumed)."""
        safe = resolve_within_root(path, self._root)
        if safe is None:
            return f"Access denied: {path!r} is outside the project repo.", 0
        if not safe.is_file():
            return f"File not found: {path}", 0

        text = safe.read_text(encoding="utf-8")
        tokens = TokenCounter.estimate(text)
        if tokens > remaining_budget:
            char_budget = remaining_budget * 4
            text = (
                f"{text[:char_budget]}\n"
                f"... [truncated: {tokens} tokens total, budget allows ~{remaining_budget}]"
            )
            tokens = remaining_budget
        return text, tokens

    # ── prompt building ───────────────────────────────────────────────────────

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
            "correctness without additional context.\n\n"
            "If you need to verify a specific behavioral or architectural claim that isn't covered "
            "by the Code Context above — for example, confirming what a referenced function or "
            "callback actually receives — you may instead respond with:\n"
            '{"action": "request_file", "path": "repo/relative/path.py", "reason": "..."}\n'
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
