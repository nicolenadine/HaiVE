from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from haive.execution.review_agent import REVIEWER_MODELS, ReviewAgent
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.model_client import ModelClient
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


def make_turn(payload: dict) -> AgenticTurn:
    return AgenticTurn(tool_calls=[], content=json.dumps(payload), model_used="mock")


def _tool_call(name: str, **kwargs) -> ToolCall:
    return ToolCall(id=f"tc_{name}", name=name, arguments=kwargs)


def _turn_with_tools(*tool_calls: ToolCall) -> AgenticTurn:
    return AgenticTurn(tool_calls=list(tool_calls), content=None, model_used="mock")


def make_agent(client: ModelClient, root: str = "/tmp") -> ReviewAgent:
    return ReviewAgent(client, SYSTEM_PROMPT, GUIDELINES, root)


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
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert verdict.passed is True
        assert verdict.uncertain is False
        assert verdict.suggestions == []

    def test_failing_output_returns_failed_verdict_with_suggestions(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(FAILING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert verdict.passed is False
        assert verdict.uncertain is False
        assert len(verdict.suggestions) > 0

    def test_failing_verdict_suggestions_come_from_findings(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(FAILING_PAYLOAD)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert "Add retry decorator" in verdict.suggestions


# ── model escalation ──────────────────────────────────────────────────────────

class TestModelEscalation:
    def test_uncertain_advances_to_next_model(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [
            make_turn(UNCERTAIN_PAYLOAD),
            make_turn(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert client.call_single.call_count == 2
        assert verdict.passed is True

    def test_all_uncertain_defaults_to_failed(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [make_turn(UNCERTAIN_PAYLOAD)] * len(REVIEWER_MODELS)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert client.call_single.call_count == len(REVIEWER_MODELS)
        assert verdict.passed is False
        assert verdict.uncertain is False

    def test_uncertain_does_not_set_uncertain_on_final_verdict(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [make_turn(UNCERTAIN_PAYLOAD)] * len(REVIEWER_MODELS)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert verdict.uncertain is False

    def test_all_models_fail_schema_validation_returns_fallback_with_raw_excerpt(self):
        # Regression test: when every reviewer model's response fails to parse
        # (e.g. truncated mid-JSON because the response ran past the token
        # budget), the fallback verdict must preserve an excerpt of the raw
        # output — otherwise a real submission's fate here is a total black
        # box, with no way to tell afterward whether the code was actually
        # fine and only the reviewer's own output generation failed.
        client = MagicMock(spec=ModelClient)
        truncated = '{"passed": false, "findings": [{"file": "a.py", "line": 1, "severity": "major", "message": "cut off mid'
        client.call_single.side_effect = [
            AgenticTurn(tool_calls=[], content=truncated, model_used=m) for m in REVIEWER_MODELS
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert verdict.passed is False
        assert "Reviewer failed to produce a valid output after all model attempts" in verdict.reason
        assert truncated[:50] in verdict.reason
        assert verdict.suggestions == ["Manual review required."]

    def test_infeasible_does_not_advance_to_next_model(self):
        client = MagicMock(spec=ModelClient)
        infeasible_payload = {
            "passed": False, "infeasible": True, "uncertain": False,
            "findings": [], "summary": "architecturally impossible",
        }
        client.call_single.return_value = make_turn(infeasible_payload)
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert client.call_single.call_count == 1
        assert verdict.infeasible is True
        assert verdict.passed is False

    def test_parse_failure_advances_to_next_model(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [
            AgenticTurn(tool_calls=[], content="not json", model_used="mock"),
            make_turn(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert verdict.passed is True


# ── prompt content ────────────────────────────────────────────────────────────

class TestPromptContent:
    def _captured_messages(self, client: MagicMock, **review_kwargs) -> list[dict]:
        defaults = dict(
            task=make_task(),
            agent_output=make_agent_output(),
            loaded_sections=[],
            discovery_status="found",
            discovery_note="",
            original_contents={},
        )
        make_agent(client).review(**(defaults | review_kwargs))
        return client.call_single.call_args.kwargs["messages"]

    def _captured_prompt(self, client: MagicMock, **review_kwargs) -> str:
        messages = self._captured_messages(client, **review_kwargs)
        return next(m["content"] for m in messages if m["role"] == "user")

    def test_task_title_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "Add retry logic" in prompt

    def test_acceptance_criteria_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "max 3 attempts" in prompt

    def test_guidelines_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)
        assert "No secrets in logs" in prompt

    def test_system_prompt_is_a_separate_message(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        messages = self._captured_messages(client)
        assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}

    def test_empty_unexpected_triggers_extra_scrutiny_note(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(
            client,
            discovery_status="empty_unexpected",
            discovery_note="No matching code found.",
        )
        assert "extra scrutiny" in prompt.lower() or "no code context" in prompt.lower()
        assert "No matching code found." in prompt

    def test_empty_expected_does_not_trigger_extra_scrutiny(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client, discovery_status="empty_expected")
        assert "extra scrutiny" not in prompt.lower()

    def test_loaded_sections_included_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        section = LoadedSection(file="haive/client.py", source="class Client: pass", reason="Core client.")
        prompt = self._captured_prompt(client, loaded_sections=[section])
        assert "haive/client.py" in prompt
        assert "class Client: pass" in prompt

    def test_execution_summary_included_in_prompt(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(
            client, execution_summary="Syntax: OK. Imports: OK. `pytest -q`: exit 0. 219 passed."
        )
        assert "Execution Verification" in prompt
        assert "219 passed" in prompt

    def test_no_execution_verification_section_when_summary_empty(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)  # default execution_summary=""
        assert "Execution Verification" not in prompt

    def test_original_file_content_included_for_edited_path(self):
        # original_contents is supplied by the caller (TaskExecutor, which
        # captures it once per task before any attempt writes to disk) —
        # ReviewAgent no longer reads it from disk itself.
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        make_agent(client).review(
            make_task(), make_agent_output(), [], "found", "",
            original_contents={"haive/client.py": "class Client:\n    def old_method(self): pass\n"},
        )
        messages = client.call_single.call_args.kwargs["messages"]
        prompt = next(m["content"] for m in messages if m["role"] == "user")
        assert "Original File Content" in prompt
        assert "old_method" in prompt

    def test_no_original_file_section_when_original_contents_empty(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        prompt = self._captured_prompt(client)  # default original_contents={}
        assert "Original File Content" not in prompt

    def test_scaffold_new_files_have_no_original_content(self):
        from haive.models.agent_output import FileToCreate, ScaffoldAgentOutput
        client = MagicMock(spec=ModelClient)
        client.call_single.return_value = make_turn(PASSING_PAYLOAD)
        scaffold_output = ScaffoldAgentOutput(
            files=[FileToCreate(path="haive/new_module.py", content="x = 1")], notes="",
        )
        make_agent(client).review(
            make_task(), scaffold_output, [], "empty_expected", "",
            original_contents={},
        )
        messages = client.call_single.call_args.kwargs["messages"]
        prompt = next(m["content"] for m in messages if m["role"] == "user")
        assert "Original File Content" not in prompt


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

    def test_infeasible_and_passed_raises(self):
        with pytest.raises(Exception):
            ReviewVerdict(passed=True, reason="ok", infeasible=True)

    def test_infeasible_and_uncertain_raises(self):
        with pytest.raises(Exception):
            ReviewVerdict(passed=False, reason="ok", uncertain=True, infeasible=True)

    def test_infeasible_allows_empty_suggestions(self):
        verdict = ReviewVerdict(passed=False, reason="architecturally impossible", infeasible=True, suggestions=[])
        assert verdict.infeasible is True
        assert verdict.suggestions == []

    def test_to_summary_carries_infeasible(self):
        verdict = ReviewVerdict(passed=False, reason="architecturally impossible", infeasible=True)
        summary = verdict.to_summary()
        assert summary.infeasible is True


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

    def test_infeasible_true_and_passed_true_raises(self):
        from haive.models.agent_output import ReviewAgentOutput
        with pytest.raises(Exception):
            ReviewAgentOutput(passed=True, infeasible=True, findings=[], summary="?")

    def test_infeasible_true_and_uncertain_true_raises(self):
        from haive.models.agent_output import ReviewAgentOutput
        with pytest.raises(Exception):
            ReviewAgentOutput(passed=False, uncertain=True, infeasible=True, findings=[], summary="?")

    def test_infeasible_true_passed_false_is_valid(self):
        from haive.models.agent_output import ReviewAgentOutput
        output = ReviewAgentOutput(passed=False, infeasible=True, findings=[], summary="?")
        assert output.infeasible is True


# ── read_file tool integration ─────────────────────────────────────────────────
# Detailed loop/budget/round-limit behavior is covered by tests/test_read_file_tool.py.
# These confirm ReviewAgent wires run_tool_loop correctly end-to-end.

class TestReadFileToolIntegration:
    def test_review_reads_requested_file_before_returning_verdict(self, tmp_path):
        (tmp_path / "extra.py").write_text("def caller(): pass")
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check the caller")),
            make_turn(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client, root=str(tmp_path)).review(
            make_task(), make_agent_output(), [], "found", "", original_contents={}
        )
        assert client.call_single.call_count == 2
        assert verdict.passed is True
        second_messages = client.call_single.call_args_list[1].kwargs["messages"]
        assert any("def caller(): pass" in (m.get("content") or "") for m in second_messages)

    def test_path_traversal_is_denied_without_raising(self, tmp_path):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="../../etc/passwd", reason="x")),
            make_turn(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client, root=str(tmp_path)).review(
            make_task(), make_agent_output(), [], "found", "", original_contents={}
        )
        assert verdict.passed is True
        second_messages = client.call_single.call_args_list[1].kwargs["messages"]
        assert any("Access denied" in (m.get("content") or "") for m in second_messages)

    def test_escalation_carries_transcript_across_models(self):
        client = MagicMock(spec=ModelClient)
        client.call_single.side_effect = [
            make_turn(UNCERTAIN_PAYLOAD),
            make_turn(PASSING_PAYLOAD),
        ]
        verdict = make_agent(client).review(make_task(), make_agent_output(), [], "found", "", original_contents={})
        assert client.call_single.call_count == 2
        assert verdict.passed is True
        first_messages = client.call_single.call_args_list[0].kwargs["messages"]
        second_messages = client.call_single.call_args_list[1].kwargs["messages"]
        assert len(second_messages) >= len(first_messages)
