"""Tests for the haive run CLI command (Step 23)."""
from __future__ import annotations

import subprocess
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from haive.cli import app
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.orchestrator import NewTask, OrchestratorOutput
from haive.models.task import Project, Task, TaskExecutionRecord, VerdictSummary
from haive.orchestration.orchestrator import OrchestratorStalledError

runner = CliRunner()
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_project(**kwargs) -> Project:
    return Project(**(dict(
        project_id="42", title="Test Project",
        description="A test project.", project_branch="haive/project-42",
    ) | kwargs))


def make_task(**kwargs) -> Task:
    return Task(**(dict(
        task_id="1", title="Add feature", description="Do the thing.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT, complexity=Complexity.LOW,
        depends_on=[], acceptance_criteria=[], status=TaskStatus.PENDING,
    ) | kwargs))


def make_new_task(**kwargs) -> NewTask:
    return NewTask(**(dict(
        title="New feature", description="Build it.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT, complexity=Complexity.LOW,
        depends_on=[], acceptance_criteria=["Works"],
    ) | kwargs))


def _mock_span_cm() -> MagicMock:
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=MagicMock())
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _base_mocks() -> dict:
    mock_settings = MagicMock()
    mock_settings.max_recovery_depth = 3
    mock_settings.dry_run = False
    # Single-wave by default so existing single-wave-focused tests are unaffected by
    # the run loop; multi-wave behavior is tested explicitly with its own settings.
    mock_settings.max_waves_per_run = 1

    mock_pm = MagicMock()
    mock_pm.get_project.return_value = make_project()
    mock_pm.get_tasks.return_value = []
    mock_pm.read_new_comments.return_value = []
    mock_pm.create_task.return_value = make_task(task_id="101", title="New feature")

    mock_vcs = MagicMock()
    mock_vcs.create_project_pr.return_value = "https://github.com/owner/repo/pull/1"

    mock_state = MagicMock()
    mock_state.last_run_at = None
    mock_state.created_at = _NOW
    mock_state.tasks = {}

    mock_state_store = MagicMock()
    mock_state_store.load_or_init.return_value = mock_state

    mock_orchestrator = MagicMock()
    mock_orchestrator.run_loop.return_value = OrchestratorOutput(
        done=False, new_tasks=[make_new_task()]
    )

    mock_registry = MagicMock()
    mock_registry.get_orchestrator_summary.return_value = "summary"
    mock_registry.get_agent.return_value = MagicMock(system_prompt="prompts/reviewer.md")

    mock_tier_config = MagicMock()
    mock_tier_config.orchestrator.context_budget = 8000

    mock_scheduler = MagicMock()

    return dict(
        settings=mock_settings, pm=mock_pm, vcs=mock_vcs,
        state=mock_state, state_store=mock_state_store,
        orchestrator=mock_orchestrator, registry=mock_registry,
        tier_config=mock_tier_config, scheduler=mock_scheduler,
    )


def _run_with_mocks(
    m: dict,
    extra_args: list[str] | None = None,
    root: str = "/fake/root",
    agent_md_exists: bool = True,
    catch_exceptions: bool = False,
) -> object:
    """Invoke 'haive run --project 42' with all heavy dependencies mocked.

    All haive imports inside the run() function body are local, so we patch
    them at their source-module paths rather than haive.cli.X.
    """
    args = ["run", "--project", "42"] + (extra_args or [])
    with ExitStack() as stack:
        stack.enter_context(patch("haive.cli._check_git_on_path"))
        stack.enter_context(patch("haive.cli._check_active_config"))
        stack.enter_context(patch("haive.models.config.load_settings", return_value=m["settings"]))
        stack.enter_context(patch("haive.adapters.pm.github.GitHubPMAdapter", return_value=m["pm"]))
        stack.enter_context(patch("haive.adapters.vcs.github.GitHubVCSAdapter", return_value=m["vcs"]))
        stack.enter_context(patch("haive.persistence.state_store.StateStore", return_value=m["state_store"]))
        reg_cls = stack.enter_context(patch("haive.registry.agent_registry.AgentRegistry"))
        tc_cls = stack.enter_context(patch("haive.llm.tier_config.TierConfig"))
        stack.enter_context(patch("haive.llm.model_client.ModelClient"))
        stack.enter_context(patch("haive.discovery.code_discovery_agent.CodeDiscoveryAgent"))
        fi_cls = stack.enter_context(patch("haive.discovery.file_index_service.FileIndexService"))
        stack.enter_context(patch("haive.orchestration.orchestrator.Orchestrator", return_value=m["orchestrator"]))
        stack.enter_context(patch("haive.orchestration.task_scheduler.TaskScheduler", return_value=m["scheduler"]))
        stack.enter_context(patch("haive.execution.review_agent.ReviewAgent"))
        stack.enter_context(patch("haive.execution.task_executor.TaskExecutor"))
        stack.enter_context(patch("haive.observability.setup.setup_observability"))
        stack.enter_context(patch("haive.observability.spans.run_span", return_value=_mock_span_cm()))
        stack.enter_context(patch("haive.orchestration.example_library.ExampleLibrary"))
        stack.enter_context(patch("haive.orchestration.task_view_builder.TaskViewBuilder"))
        mock_sp = stack.enter_context(patch("subprocess.check_output"))
        stack.enter_context(patch("os.getcwd", return_value=root))
        agent_mds = [Path("/fake/agent.md")] if agent_md_exists else []
        stack.enter_context(patch("pathlib.Path.rglob", return_value=iter(agent_mds)))
        stack.enter_context(patch("pathlib.Path.read_text", return_value="system prompt"))

        reg_cls.load.return_value = m["registry"]
        tc_cls.from_settings.return_value = m["tier_config"]
        fi_cls.return_value.read_repo_map.return_value = ""
        mock_sp.return_value = b"step-23-cli\n"

        return runner.invoke(app, args, catch_exceptions=catch_exceptions)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRunPreflightAgentMd:
    def test_exits_with_error_if_no_agent_md(self):
        m = _base_mocks()
        result = _run_with_mocks(m, agent_md_exists=False)
        assert result.exit_code == 1
        assert "haive index" in result.output

    def test_proceeds_when_agent_md_exists(self):
        m = _base_mocks()
        result = _run_with_mocks(m, agent_md_exists=True)
        assert result.exit_code == 0


class TestRunDryRun:
    def test_dry_run_prints_plan_without_scheduler(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(
            done=False, new_tasks=[make_new_task(title="My Task")]
        )
        result = _run_with_mocks(m, extra_args=["--dry-run"])
        assert result.exit_code == 0
        # dry-run shows task title
        assert "My Task" in result.output
        # scheduler NOT started
        m["scheduler"].start.assert_not_called()
        # PM create_task NOT called
        m["pm"].create_task.assert_not_called()

    def test_dry_run_done_true_shows_completion(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(done=True, new_tasks=[])
        result = _run_with_mocks(m, extra_args=["--dry-run"])
        assert result.exit_code == 0
        assert "complete" in result.output.lower()


class TestRunDoneTrue:
    def test_done_true_creates_project_pr(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(done=True, new_tasks=[])
        result = _run_with_mocks(m)
        assert result.exit_code == 0
        m["vcs"].create_project_pr.assert_called_once()
        assert "Project complete" in result.output

    def test_done_true_does_not_run_scheduler(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(done=True, new_tasks=[])
        _run_with_mocks(m)
        m["scheduler"].start.assert_not_called()


class TestRunTaskCreation:
    def test_new_tasks_created_in_order(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(
            done=False,
            new_tasks=[make_new_task(title="A"), make_new_task(title="B")],
        )
        m["pm"].create_task.side_effect = [
            make_task(task_id="101", title="A"),
            make_task(task_id="102", title="B"),
        ]
        _run_with_mocks(m)
        assert m["pm"].create_task.call_count == 2

    def test_intrawave_dep_ref_resolved_before_set_dependency(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(
            done=False,
            new_tasks=[
                make_new_task(title="A", depends_on=[]),
                make_new_task(title="B", depends_on=["new:0"]),
            ],
        )
        m["pm"].create_task.side_effect = [
            make_task(task_id="101", title="A"),
            make_task(task_id="102", title="B"),
        ]
        _run_with_mocks(m)
        # "new:0" must be resolved to the real ID "101" before calling set_dependency
        m["pm"].set_dependency.assert_called_once_with("102", ["101"])

    def test_no_set_dependency_when_no_deps(self):
        m = _base_mocks()
        m["orchestrator"].run_loop.return_value = OrchestratorOutput(
            done=False,
            new_tasks=[make_new_task(depends_on=[])],
        )
        _run_with_mocks(m)
        m["pm"].set_dependency.assert_not_called()


class TestRunWaveSummary:
    def test_wave_summary_printed_after_scheduler(self):
        m = _base_mocks()
        m["pm"].get_tasks.return_value = [make_task(status=TaskStatus.COMPLETE)]
        result = _run_with_mocks(m)
        assert result.exit_code == 0
        assert "Wave 1 complete" in result.output

    def test_scheduler_receives_on_complete_callback(self):
        m = _base_mocks()
        _run_with_mocks(m)
        call_kwargs = m["scheduler"].start.call_args
        assert call_kwargs is not None
        # on_complete is the 4th positional or keyword arg
        _, kwargs = call_kwargs
        assert "on_complete" in kwargs and kwargs["on_complete"] is not None


class TestRunAutonomousWaveLoop:
    def test_second_wave_runs_automatically_until_done(self):
        m = _base_mocks()
        m["settings"].max_waves_per_run = 2
        m["orchestrator"].run_loop.side_effect = [
            OrchestratorOutput(done=False, new_tasks=[make_new_task(title="A")]),
            OrchestratorOutput(done=True, new_tasks=[]),
        ]
        result = _run_with_mocks(m)
        assert result.exit_code == 0
        assert m["orchestrator"].run_loop.call_count == 2
        assert m["scheduler"].start.call_count == 1
        m["vcs"].create_project_pr.assert_called_once()

    def test_stops_at_wave_cap_without_error(self):
        m = _base_mocks()
        m["settings"].max_waves_per_run = 2
        # Default orchestrator mock always returns done=False with a new task.
        result = _run_with_mocks(m)
        assert result.exit_code == 0
        assert m["orchestrator"].run_loop.call_count == 2
        assert "automatic wave limit" in result.output.lower()

    def test_orchestrator_stalled_error_stops_gracefully(self):
        m = _base_mocks()
        m["settings"].max_waves_per_run = 2
        m["orchestrator"].run_loop.side_effect = OrchestratorStalledError(
            "Orchestrator returned empty new_tasks without signaling done."
        )
        result = _run_with_mocks(m, catch_exceptions=True)
        assert result.exit_code == 0
        assert "waiting on human input" in result.output
        assert m["orchestrator"].run_loop.call_count == 1
        m["scheduler"].start.assert_not_called()
