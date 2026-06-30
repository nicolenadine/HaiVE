from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from haive.execution.output_validator import OutputValidationError
from haive.execution.review_agent import ReviewAgent
from haive.execution.task_executor import TaskExecutor, _apply_output
from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.model_response import ModelResponse
from haive.llm.tier import Tier
from haive.llm.tier_config import TierConfig
from haive.models.agent_output import CodeEditorOutput, FileEdit, FileToCreate, ScaffoldAgentOutput
from haive.models.config import AgentConfig
from haive.models.discovery import DiscoveredSection, DiscoveryResult, LoadedSection
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.review import ReviewVerdict
from haive.models.state import ProjectState
from haive.models.task import Task, TaskExecutionRecord, VerdictSummary

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── fixtures ──────────────────────────────────────────────────────────────────

def make_task(**kwargs) -> Task:
    defaults = dict(
        task_id="42",
        title="Add retry logic",
        description="Wrap HTTP calls with exponential backoff.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.LOW,
        depends_on=[],
        acceptance_criteria=["retries on 5xx", "max 3 attempts"],
        status=TaskStatus.PENDING,
    )
    return Task(**(defaults | kwargs))


def make_tier(max_attempts: int = 2) -> Tier:
    return Tier(models=["test-model"], max_attempts=max_attempts, context_budget=8000)


def make_tier_config(low_attempts: int = 2, medium_attempts: int = 2) -> TierConfig:
    return TierConfig(
        low=make_tier(low_attempts),
        medium=make_tier(medium_attempts),
        high=make_tier(1),
        orchestrator=make_tier(1),
        reviewer=make_tier(1),
    )


def make_agent_config(**kwargs) -> AgentConfig:
    defaults = dict(
        role=AgentRole.IMPLEMENTATION_AGENT,
        description="Implementation agent.",
        skills=["python"],
        system_prompt="prompts/implementation_agent.md",
        output_schema="CodeEditorOutput",
        max_tokens=4096,
        retry_limit=2,
        prompt_version="v1",
    )
    return AgentConfig(**(defaults | kwargs))


def make_editor_response() -> ModelResponse:
    payload = {
        "edits": [{"path": "haive/client.py", "content": "class Client: pass"}],
        "notes": "",
    }
    return ModelResponse(content=json.dumps(payload), model_used="test-model", token_usage=None)


def make_passing_review() -> ReviewVerdict:
    return ReviewVerdict(passed=True, reason="LGTM", suggestions=[])


def make_failing_review(suggestions: list[str] | None = None) -> ReviewVerdict:
    return ReviewVerdict(
        passed=False,
        reason="Missing retry logic.",
        suggestions=suggestions or ["Add retry decorator"],
    )


def make_discovery_result(*, has_sections: bool = False) -> DiscoveryResult:
    sections = (
        [DiscoveredSection(file="haive/client.py", symbol=None, start_line=None, end_line=None, full=True, reason="Core.")]
        if has_sections
        else []
    )
    return DiscoveryResult(sections=sections, status="found" if has_sections else "empty")


def make_executor(tmp_path, *, low_attempts: int = 2, medium_attempts: int = 2) -> TaskExecutor:
    return TaskExecutor(
        model_client=MagicMock(spec=ModelClient),
        tier_config=make_tier_config(low_attempts, medium_attempts),
        review_agent=MagicMock(spec=ReviewAgent),
        root=str(tmp_path),
        project_branch="main",
    )


def make_services(tmp_path):
    """Return a dict of all per-run service mocks."""
    registry = MagicMock()
    registry.get_agent.return_value = make_agent_config()

    # Write a minimal system prompt file the executor can read
    prompt_path = tmp_path / "prompts" / "implementation_agent.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("You are an implementation agent.")

    return dict(
        project_id="proj-1",
        project_state=ProjectState(
            schema_version="1", project_id="proj-1",
            created_at=_NOW, updated_at=_NOW,
        ),
        discovery_agent=MagicMock(),
        file_index=MagicMock(),
        registry=registry,
        pm=MagicMock(),
        vcs=MagicMock(),
        state_store=MagicMock(),
    )


# ── happy path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_pass_on_first_attempt(self, tmp_path):
        executor = make_executor(tmp_path)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-99"

        with patch("haive.execution.task_executor.get_changed_files", return_value=["haive/client.py"]):
            record = executor.run(make_task(), **svc)

        assert record.verdict is not None
        assert record.verdict.passed is True
        assert record.pr_id == "pr-99"
        assert record.total_attempts == 1
        svc["pm"].update_status.assert_called_with(make_task().task_id, TaskStatus.COMPLETE)
        svc["vcs"].create_branch.assert_called_once_with("haive/task-42", "main")
        svc["vcs"].merge_pr.assert_called_once_with("pr-99")

    def test_changed_files_sourced_from_get_changed_files(self, tmp_path):
        executor = make_executor(tmp_path)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=["x.py", "y.py"]):
            record = executor.run(make_task(), **svc)

        svc["vcs"].push_commits.assert_called_once()
        _, args, _ = svc["vcs"].push_commits.mock_calls[0]
        assert args[1] == ["x.py", "y.py"]
        assert record.changed_files == ["x.py", "y.py"]

    def test_update_after_task_called_with_changed_files(self, tmp_path):
        executor = make_executor(tmp_path)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=["changed.py"]):
            executor.run(make_task(), **svc)

        svc["file_index"].update_after_task.assert_called_once_with(["changed.py"], str(tmp_path))


# ── retry / feedback ──────────────────────────────────────────────────────────

class TestRetry:
    def test_retry_injects_suggestions_as_feedback(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=2)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.side_effect = [
            make_failing_review(["fix import"]),
            make_passing_review(),
        ]
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        assembled_calls: list = []
        original_assemble = executor._assembler.assemble

        def capture_assemble(**kwargs):
            assembled_calls.append(kwargs.get("retry_feedback"))
            return original_assemble(**kwargs)

        executor._assembler.assemble = capture_assemble

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            record = executor.run(make_task(), **svc)

        assert record.total_attempts == 2
        assert assembled_calls[0] is None      # first attempt has no feedback
        assert assembled_calls[1] == ["fix import"]  # second attempt gets suggestions

    def test_schema_failure_skips_reviewer(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=2)
        svc = make_services(tmp_path)

        executor._model_client.call.side_effect = [
            ModelResponse(content="not json", model_used="test-model", token_usage=None),
            make_editor_response(),
        ]
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            executor.run(make_task(), **svc)

        # reviewer called only once (second attempt), not for the schema-failed first attempt
        assert executor._review_agent.review.call_count == 1

    def test_schema_failure_logged_in_attempt_log(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=2)
        svc = make_services(tmp_path)

        executor._model_client.call.side_effect = [
            ModelResponse(content="not json", model_used="test-model", token_usage=None),
            make_editor_response(),
        ]
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            record = executor.run(make_task(), **svc)

        schema_entries = [e for e in record.attempt_log if "Schema" in e.reason]
        assert len(schema_entries) == 1


# ── tier escalation ───────────────────────────────────────────────────────────

class TestTierEscalation:
    def test_escalates_to_medium_after_low_exhausted(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=1, medium_attempts=1)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.side_effect = [
            make_failing_review(),    # LOW tier fails
            make_passing_review(),    # MEDIUM tier passes
        ]
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            record = executor.run(make_task(complexity=Complexity.LOW), **svc)

        # discovery called twice: once per tier
        assert svc["discovery_agent"].discover.call_count == 2
        assert record.verdict is not None
        assert record.verdict.passed is True

    def test_all_tiers_exhausted_sets_needs_human_review(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=1, medium_attempts=1)
        svc = make_services(tmp_path)

        executor._tier_config.high = make_tier(max_attempts=1)
        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_failing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []

        record = executor.run(make_task(complexity=Complexity.LOW), **svc)

        svc["pm"].update_status.assert_called_with("42", TaskStatus.NEEDS_HUMAN_REVIEW)
        svc["pm"].add_comment.assert_called_once()
        assert record.verdict is None
        assert record.total_attempts == 3  # 1 per tier

    def test_starts_at_task_complexity_not_low(self, tmp_path):
        executor = make_executor(tmp_path, medium_attempts=1)
        svc = make_services(tmp_path)

        executor._tier_config.high = make_tier(max_attempts=1)
        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            record = executor.run(make_task(complexity=Complexity.MEDIUM), **svc)

        # LOW tier never ran — only one discover() call
        assert svc["discovery_agent"].discover.call_count == 1
        assert record.tier_used == Complexity.MEDIUM


# ── discovery status ──────────────────────────────────────────────────────────

class TestDiscoveryStatus:
    def _get_discovery_arg(self, review_mock) -> str:
        _, _, kwargs = review_mock.mock_calls[0]
        return kwargs.get("discovery_status") or review_mock.call_args[0][3]

    def test_non_scaffold_empty_discovery_is_unexpected(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=1)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result(has_sections=False)
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            executor.run(make_task(agent_role=AgentRole.IMPLEMENTATION_AGENT), **svc)

        call_kwargs = executor._review_agent.review.call_args
        status = call_kwargs.kwargs.get("discovery_status") or call_kwargs[0][3]
        assert status == "empty_unexpected"

    def test_scaffold_empty_discovery_is_expected(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=1)
        svc = make_services(tmp_path)

        svc["registry"].get_agent.return_value = make_agent_config(
            role=AgentRole.SCAFFOLD_AGENT,
            system_prompt="prompts/implementation_agent.md",
        )
        executor._model_client.call.return_value = ModelResponse(
            content=json.dumps({"files": [{"path": "new.py", "content": "x=1"}], "notes": ""}),
            model_used="test-model",
            token_usage=None,
        )
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result(has_sections=False)
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            executor.run(make_task(agent_role=AgentRole.SCAFFOLD_AGENT), **svc)

        call_kwargs = executor._review_agent.review.call_args
        status = call_kwargs.kwargs.get("discovery_status") or call_kwargs[0][3]
        assert status == "empty_expected"

    def test_found_sections_yields_found_status(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=1)
        svc = make_services(tmp_path)

        executor._model_client.call.return_value = make_editor_response()
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result(has_sections=True)
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            executor.run(make_task(), **svc)

        call_kwargs = executor._review_agent.review.call_args
        status = call_kwargs.kwargs.get("discovery_status") or call_kwargs[0][3]
        assert status == "found"


# ── file application ──────────────────────────────────────────────────────────

class TestFileApplication:
    def test_scaffold_output_files_written_to_disk(self, tmp_path):
        output = ScaffoldAgentOutput(
            files=[
                FileToCreate(path="pkg/__init__.py", content="# pkg"),
                FileToCreate(path="pkg/module.py", content="x = 1"),
            ],
            notes="",
        )
        _apply_output(output, str(tmp_path))
        assert (tmp_path / "pkg" / "__init__.py").read_text() == "# pkg"
        assert (tmp_path / "pkg" / "module.py").read_text() == "x = 1"

    def test_editor_output_file_written_to_disk(self, tmp_path):
        output = CodeEditorOutput(
            edits=[FileEdit(path="haive/client.py", content="class Client: pass")],
            notes="",
        )
        _apply_output(output, str(tmp_path))
        assert (tmp_path / "haive" / "client.py").read_text() == "class Client: pass"

    def test_nested_directories_created_automatically(self, tmp_path):
        output = ScaffoldAgentOutput(
            files=[FileToCreate(path="a/b/c/deep.py", content="deep = True")],
            notes="",
        )
        _apply_output(output, str(tmp_path))
        assert (tmp_path / "a" / "b" / "c" / "deep.py").exists()


# ── API error handling ────────────────────────────────────────────────────────

class TestAPIErrorHandling:
    def test_api_error_does_not_advance_attempt_counter(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=2)
        svc = make_services(tmp_path)

        executor._model_client.call.side_effect = [
            APIError("timeout"),
            make_editor_response(),
        ]
        executor._review_agent.review.return_value = make_passing_review()
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []
        svc["vcs"].create_pr.return_value = "pr-1"

        with patch("haive.execution.task_executor.get_changed_files", return_value=[]):
            record = executor.run(make_task(), **svc)

        assert record.total_attempts == 1

    def test_consecutive_api_errors_exceeding_max_reraises(self, tmp_path):
        executor = make_executor(tmp_path, low_attempts=5)
        svc = make_services(tmp_path)

        executor._model_client.call.side_effect = APIError("persistent failure")
        svc["discovery_agent"].discover.return_value = make_discovery_result()
        svc["file_index"].load_sections.return_value = []

        with pytest.raises(APIError):
            executor.run(make_task(), **svc)
