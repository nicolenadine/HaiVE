from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from haive.execution.review_agent import REVIEWER_MODELS, ReviewAgent
from haive.llm.model_client import ModelClient
from haive.llm.model_response import ModelResponse
from haive.models.agent_output import CodeEditorOutput, FileEdit
from haive.models.discovery import LoadedSection
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.review import ReviewVerdict
from haive.models.task import Task


# ── fixtures ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = "You are a code reviewer. Evaluate the submission."
GUIDELINES = "Write correct, readable code. No secrets in logs."


def make_task(**kwargs) -> Task:
    defaults = dict(
        task_id="1",
        title="Add retry logic",
        description="Wrap HTTP calls with exponential backoff.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.LOW,
        depends_on=[],
        acceptance_criteria=["retries on 5xx", "max 3 attempts"],
        status=TaskStatus.IN_PROGRESS,
    )
    return Task(**(defaults | kwargs))


def make_agent_output() -> CodeEditorOutput:
    return CodeEditorOutput(
        edits=[FileEdit(path="haive/client.py", content="class Client: pass")],
        notes="",
    )


def make_response(payload: dict) -> ModelResponse:
    return ModelResponse(content=json.dumps(payload), model_used="mock", token_usage=None)


def make_agent(client: ModelClient) -> ReviewAgent:
    return ReviewAgent(client, SYSTEM_PROMPT, GUIDELINES)


PASSING_PAYLOAD = {"passed": True, "uncertain": False, "findings": [], "summary": "LGTM"}
FAILING_PAYLOAD = {
    "passed": False,
    "uncertain": False,
    "findings": [{"file": "client.py", "line": 1, "severity": "major", "message": "Missing retry", "suggestion": "Add retry decorator"}],
    "summary": "Missing retry logic.",
}
UNCERTAIN_PAYLOAD = {"passed": False, "uncertain": True, "findings": [], "summary": "Cannot determine."}


# ── verdict content ───────────────────────────────────────────────────────────

class TestVerdictContent:
    def test_passing_output_returns_passed_verdict(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert verdict.passed is True
        assert verdict.uncertain is False
        assert verdict.suggestions == []

    def test_failing_output_returns_failed_verdict_with_suggestions(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(FAILING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert verdict.passed is False
        assert verdict.uncertain is False
        assert len(verdict.suggestions) > 0

    def test_failing_verdict_suggestions_come_from_findings(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(FAILING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert "Add retry decorator" in verdict.suggestions


# ── model escalation ──────────────────────────────────────────────────────────

class TestModelEscalation:
    def test_uncertain_advances_to_next_model(self):
        client = MagicMock(spec=ModelClient)
        client.call.side_effect = [
            make_response(UNCERTAIN_PAYLOAD),
            make_response(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert client.call.call_count == 2
        assert verdict.passed is True

    def test_all_uncertain_defaults_to_failed(self):
        client = MagicMock(spec=ModelClient)
        client.call.side_effect = [make_response(UNCERTAIN_PAYLOAD)] * len(REVIEWER_MODELS)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert client.call.call_count == len(REVIEWER_MODELS)
        assert verdict.passed is False
        assert verdict.uncertain is False

    def test_uncertain_does_not_set_uncertain_on_final_verdict(self):
        client = MagicMock(spec=ModelClient)
        client.call.side_effect = [make_response(UNCERTAIN_PAYLOAD)] * len(REVIEWER_MODELS)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert verdict.uncertain is False

    def test_parse_failure_advances_to_next_model(self):
        client = MagicMock(spec=ModelClient)
        client.call.side_effect = [
            ModelResponse(content="not json", model_used="mock", token_usage=None),
            make_response(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "")
        assert verdict.passed is True


# ── prompt content ────────────────────────────────────────────────────────────

class TestPromptContent:
    def _captured_prompt(self, client: MagicMock, **review_kwargs) -> str:
        defaults = dict(
            task=make_task(),
            agent_output=make_agent_output(),
            loaded_sections=[],
            discovery_status="found",
            discovery_note="",
        )
        make_agent(client).review(**(defaults | review_kwargs))
        return client.call.call_args.kwargs["prompt"]

    def test_task_title_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "Add retry logic" in prompt

    def test_acceptance_criteria_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "max 3 attempts" in prompt

    def test_guidelines_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "No secrets in logs" in prompt

    def test_empty_unexpected_triggers_extra_scrutiny_note(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        prompt = self._captured_prompt(
            client,
            discovery_status="empty_unexpected",
            discovery_note="No matching code found.",
        )
        assert "extra scrutiny" in prompt.lower() or "no code context" in prompt.lower()
        assert "No matching code found." in prompt

    def test_empty_expected_does_not_trigger_extra_scrutiny(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client, discovery_status="empty_expected")
        assert "extra scrutiny" not in prompt.lower()

    def test_loaded_sections_included_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call.return_value = make_response(PASSING_PAYLOAD)
        section = LoadedSection(file="haive/client.py", source="class Client: pass", reason="Core client.")
        prompt = self._captured_prompt(client, loaded_sections=[section])
        assert "haive/client.py" in prompt
        assert "class Client: pass" in prompt


# ── ReviewVerdict model ───────────────────────────────────────────────────────

class TestReviewVerdict:
    def test_uncertain_and_passed_raises(self):
        with pytest.raises(Exception):
            ReviewVerdict(passed=True, reason="ok", uncertain=True)

    def test_failed_without_suggestions_raises(self):
        with pytest.raises(Exception):
            ReviewVerdict(passed=False, reason="bad", suggestions=[])

    def test_to_summary_strips_suggestions(self):
        verdict = ReviewVerdict(passed=False, reason="bad", suggestions=["fix it"])
        summary = verdict.to_summary()
        assert summary.passed is False
        assert summary.reason == "bad"
        assert not hasattr(summary, "suggestions")

    def test_passing_verdict_allows_empty_suggestions(self):
        verdict = ReviewVerdict(passed=True, reason="LGTM", suggestions=[])
        assert verdict.passed is True


# ── ReviewAgentOutput schema ──────────────────────────────────────────────────

class TestReviewAgentOutputSchema:
    def test_uncertain_true_and_passed_true_raises(self):
        from haive.models.agent_output import ReviewAgentOutput
        with pytest.raises(Exception):
            ReviewAgentOutput(passed=True, uncertain=True, findings=[], summary="?")

    def test_uncertain_true_passed_false_is_valid(self):
        from haive.models.agent_output import ReviewAgentOutput
        output = ReviewAgentOutput(passed=False, uncertain=True, findings=[], summary="?")
        assert output.uncertain is True
