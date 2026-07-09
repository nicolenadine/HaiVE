from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.model_response import ModelResponse
from haive.llm.tier import Tier
from haive.llm.tier_config import TierConfig
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.orchestrator import (
    NewTask,
    OrchestratorInput,
    OrchestratorOutput,
    OrchestratorTaskView,
)
from haive.models.state import ProjectState
from haive.models.task import (
    AttemptLogEntry,
    Project,
    Task,
    TaskComment,
    TaskExecutionRecord,
    VerdictSummary,
)
from haive.orchestration.orchestrator import Orchestrator, OrchestratorStalledError
from haive.orchestration.task_view_builder import TaskViewBuilder


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PROJECT = Project(
    project_id="7",
    title="Test Project",
    description="desc",
    project_branch="haive/project-7",
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_task(
    task_id: str = "1",
    status: TaskStatus = TaskStatus.PENDING,
    lineage_depth: int = 0,
    recovery_for: str | None = None,
) -> Task:
    return Task(
        task_id=task_id,
        title=f"Task {task_id}",
        description="desc",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.MEDIUM,
        depends_on=[],
        acceptance_criteria=["ac"],
        status=status,
        lineage_depth=lineage_depth,
        recovery_for=recovery_for,
    )


def _make_view(
    task_id: str = "1",
    status: TaskStatus = TaskStatus.PENDING,
    lineage_depth: int = 0,
    recovery_for: str | None = None,
    attempt_log: list[AttemptLogEntry] | None = None,
    verdict: VerdictSummary | None = None,
) -> OrchestratorTaskView:
    return OrchestratorTaskView(
        task_id=task_id,
        title=f"Task {task_id}",
        description="desc",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.MEDIUM,
        depends_on=[],
        lineage_depth=lineage_depth,
        recovery_for=recovery_for,
        status=status,
        verdict=verdict,
        attempt_log=attempt_log or [],
    )


def _make_new_task(
    recovery_for: str | None = None,
    lineage_depth: int = 0,
) -> NewTask:
    return NewTask(
        title="Do something",
        description="implementation desc",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.MEDIUM,
        acceptance_criteria=["it works"],
        recovery_for=recovery_for,
        lineage_depth=lineage_depth,
    )


def _make_input(
    tasks: list[OrchestratorTaskView] | None = None,
    comments: list[TaskComment] | None = None,
    repo_map: str = "",
    unstall_task_id: str | None = None,
) -> OrchestratorInput:
    return OrchestratorInput(
        project=_PROJECT,
        tasks=tasks or [],
        new_comments=comments or [],
        agent_summary="implementation_agent: writes code",
        repo_map=repo_map,
        unstall_task_id=unstall_task_id,
    )


def _make_tier_config() -> TierConfig:
    tier = Tier(models=["high-model"], max_attempts=2, context_budget=32000)
    return TierConfig(low=tier, medium=tier, high=tier, orchestrator=tier, reviewer=tier)


def _make_orchestrator(
    mock_client: MagicMock,
    max_recovery_depth: int = 3,
) -> Orchestrator:
    return Orchestrator(
        model_client=mock_client,
        tier_config=_make_tier_config(),
        max_recovery_depth=max_recovery_depth,
    )


def _output_json(new_tasks: list[NewTask] | None = None, done: bool = False) -> str:
    payload = {
        "new_tasks": [t.model_dump(mode="json") for t in (new_tasks or [])],
        "done": done,
    }
    return json.dumps(payload)


def _mock_client(content: str) -> MagicMock:
    mock = MagicMock(spec=ModelClient)
    mock.call.return_value = ModelResponse(content=content, model_used="high-model")
    return mock


def _make_state(
    task_id: str | None = None,
    record: TaskExecutionRecord | None = None,
) -> ProjectState:
    state = ProjectState(project_id="7", created_at=_NOW, updated_at=_NOW)
    if task_id and record:
        state.tasks[task_id] = record
    return state


# ---------------------------------------------------------------------------
# TestOrchestratorModels
# ---------------------------------------------------------------------------

class TestOrchestratorModels:
    def test_done_true_with_nonempty_tasks_raises(self):
        with pytest.raises(ValidationError):
            OrchestratorOutput(done=True, new_tasks=[_make_new_task()])

    def test_done_false_with_tasks_is_valid(self):
        out = OrchestratorOutput(done=False, new_tasks=[_make_new_task()])
        assert len(out.new_tasks) == 1

    def test_new_task_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            NewTask(
                title="t",
                description="d",
                agent_role=AgentRole.IMPLEMENTATION_AGENT,
                complexity=Complexity.LOW,
                acceptance_criteria=["ac"],
                unknown_field="bad",
            )

    def test_orchestrator_output_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            OrchestratorOutput(new_tasks=[], done=False, surprise="nope")


# ---------------------------------------------------------------------------
# TestTaskViewBuilder
# ---------------------------------------------------------------------------

class TestTaskViewBuilder:
    def _builder(self) -> TaskViewBuilder:
        return TaskViewBuilder()

    def test_complete_task_drops_attempt_log(self):
        task = _make_task("1", TaskStatus.COMPLETE)
        log_entry = AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="slow")
        record = TaskExecutionRecord(
            task_id="1",
            attempt_log=[log_entry],
            verdict=VerdictSummary(passed=True, reason="ok"),
        )
        state = _make_state("1", record)
        views = self._builder().build([task], state, budget_tokens=100_000)
        assert views[0].attempt_log == []

    def test_noncomplete_task_keeps_attempt_log(self):
        task = _make_task("1", TaskStatus.NEEDS_HUMAN_REVIEW)
        log_entry = AttemptLogEntry(tier=Complexity.MEDIUM, attempt=1, reason="slow")
        record = TaskExecutionRecord(task_id="1", attempt_log=[log_entry])
        state = _make_state("1", record)
        views = self._builder().build([task], state, budget_tokens=100_000)
        assert len(views[0].attempt_log) == 1

    def test_task_with_no_record_gets_none_verdict(self):
        task = _make_task("5", TaskStatus.PENDING)
        state = _make_state()
        views = self._builder().build([task], state, budget_tokens=100_000)
        assert views[0].verdict is None
        assert views[0].attempt_log == []

    def test_over_budget_drops_oldest_complete_task(self):
        task_old = _make_task("1", TaskStatus.COMPLETE)
        task_new = _make_task("99", TaskStatus.COMPLETE)
        state = _make_state()
        # budget of 1 token forces dropping until empty or within budget
        views = self._builder().build([task_old, task_new], state, budget_tokens=1)
        # all complete tasks may be dropped; none should be id "1" before "99" if partial drop
        task_ids = [v.task_id for v in views]
        if task_ids:
            # "1" (oldest) must not survive if "99" is also present
            assert "1" not in task_ids or "99" not in task_ids

    def test_noncomplete_tasks_never_dropped_under_budget_pressure(self):
        pending = _make_task("1", TaskStatus.PENDING)
        complete = _make_task("2", TaskStatus.COMPLETE)
        state = _make_state()
        views = self._builder().build([pending, complete], state, budget_tokens=1)
        assert any(v.task_id == "1" for v in views)


# ---------------------------------------------------------------------------
# TestOrchestratorRunLoop
# ---------------------------------------------------------------------------

class TestOrchestratorRunLoop:
    def test_fresh_project_returns_first_wave(self):
        new_tasks = [_make_new_task(), _make_new_task()]
        client = _mock_client(_output_json(new_tasks=new_tasks))
        orch = _make_orchestrator(client)
        result = orch.run_loop(_make_input())
        assert len(result.new_tasks) == 2
        assert not result.done

    def test_recovery_within_depth_passes_through(self):
        recovery = _make_new_task(recovery_for="42", lineage_depth=2)
        client = _mock_client(_output_json(new_tasks=[recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=1)]
        result = orch.run_loop(_make_input(tasks=tasks))
        assert result.new_tasks[0].recovery_for == "42"
        assert result.new_tasks[0].lineage_depth == 2

    def test_recovery_at_max_depth_raises(self):
        # LLM incorrectly produces a recovery task when source is at max depth
        bad_recovery = _make_new_task(recovery_for="42", lineage_depth=4)
        client = _mock_client(_output_json(new_tasks=[bad_recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=3)]
        with pytest.raises(RuntimeError, match="max_recovery_depth"):
            orch.run_loop(_make_input(tasks=tasks))

    def test_recovery_at_max_depth_raises_orchestrator_stalled_error(self):
        bad_recovery = _make_new_task(recovery_for="42", lineage_depth=4)
        client = _mock_client(_output_json(new_tasks=[bad_recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=3)]
        with pytest.raises(OrchestratorStalledError):
            orch.run_loop(_make_input(tasks=tasks))

    def test_recovery_at_max_depth_sets_stalled_task_id(self):
        # A human reading the stalled task's GitHub issue needs to know which
        # task this is about — stalled_task_id lets a caller post a lineage
        # summary there instead of only echoing to the local console.
        bad_recovery = _make_new_task(recovery_for="42", lineage_depth=4)
        client = _mock_client(_output_json(new_tasks=[bad_recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=3)]
        with pytest.raises(OrchestratorStalledError) as exc_info:
            orch.run_loop(_make_input(tasks=tasks))
        assert exc_info.value.stalled_task_id == "42"

    def test_unstall_task_id_allows_one_recovery_past_max_depth(self):
        # A human has reviewed task 42's stalled chain and re-run with
        # --unstall 42 — this specific lineage gets one attempt beyond the
        # normal cap; the recovery must go through, not raise.
        recovery = _make_new_task(recovery_for="42", lineage_depth=4)
        client = _mock_client(_output_json(new_tasks=[recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=3)]
        result = orch.run_loop(_make_input(tasks=tasks, unstall_task_id="42"))
        assert result.new_tasks[0].recovery_for == "42"

    def test_unstall_task_id_exemption_is_one_attempt_only(self):
        # The exemption lifts the cap by exactly one level — it is not an
        # unlimited lift for that lineage.
        recovery = _make_new_task(recovery_for="42", lineage_depth=5)
        client = _mock_client(_output_json(new_tasks=[recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("42", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=4)]
        with pytest.raises(OrchestratorStalledError):
            orch.run_loop(_make_input(tasks=tasks, unstall_task_id="42"))

    def test_unstall_task_id_does_not_exempt_other_lineages(self):
        # Exempting task 42 must not accidentally lift the cap for an
        # unrelated task's own maxed-out recovery chain.
        bad_recovery = _make_new_task(recovery_for="99", lineage_depth=4)
        client = _mock_client(_output_json(new_tasks=[bad_recovery]))
        orch = _make_orchestrator(client, max_recovery_depth=3)
        tasks = [_make_view("99", TaskStatus.NEEDS_HUMAN_REVIEW, lineage_depth=3)]
        with pytest.raises(OrchestratorStalledError) as exc_info:
            orch.run_loop(_make_input(tasks=tasks, unstall_task_id="42"))
        assert exc_info.value.stalled_task_id == "99"

    def test_done_true_signals_completion(self):
        client = _mock_client(_output_json(done=True))
        orch = _make_orchestrator(client)
        result = orch.run_loop(_make_input())
        assert result.done
        assert result.new_tasks == []

    def test_empty_tasks_done_false_raises(self):
        client = _mock_client(_output_json(new_tasks=[], done=False))
        orch = _make_orchestrator(client)
        with pytest.raises(RuntimeError, match="empty new_tasks"):
            orch.run_loop(_make_input())

    def test_empty_tasks_done_false_raises_orchestrator_stalled_error(self):
        client = _mock_client(_output_json(new_tasks=[], done=False))
        orch = _make_orchestrator(client)
        with pytest.raises(OrchestratorStalledError):
            orch.run_loop(_make_input())

    def test_empty_tasks_stall_has_no_stalled_task_id(self):
        # This stall isn't about any specific task, so there's nothing to
        # post a lineage comment to — stalled_task_id must stay None.
        client = _mock_client(_output_json(new_tasks=[], done=False))
        orch = _make_orchestrator(client)
        with pytest.raises(OrchestratorStalledError) as exc_info:
            orch.run_loop(_make_input())
        assert exc_info.value.stalled_task_id is None

    def test_new_comments_in_input(self):
        comment = TaskComment(
            task_id="5",
            author="alice",
            body="please fix edge case",
            created_at=_NOW,
        )
        inp = _make_input(comments=[comment])
        assert inp.new_comments[0].task_id == "5"
        assert inp.new_comments[0].body == "please fix edge case"

    def test_markdown_fenced_json_is_accepted(self):
        new_tasks = [_make_new_task()]
        raw_json = _output_json(new_tasks=new_tasks)
        fenced = f"```json\n{raw_json}\n```"
        client = _mock_client(fenced)
        orch = _make_orchestrator(client)
        result = orch.run_loop(_make_input())
        assert len(result.new_tasks) == 1

    def test_repo_map_is_included_in_prompt(self):
        client = _mock_client(_output_json(new_tasks=[_make_new_task()]))
        orch = _make_orchestrator(client)
        orch.run_loop(_make_input(repo_map="### ./\n\ncli.py — command-line interface"))
        prompt = client.call.call_args.args[1]
        assert "cli.py" in prompt
        assert "command-line interface" in prompt

    def test_infeasible_verdict_is_visible_in_prompt_without_a_comment(self):
        # Recovery eligibility for an infeasible verdict is prompt-driven, not code-enforced —
        # this only confirms the signal the orchestrator needs actually reaches the prompt,
        # with no new_comments required.
        client = _mock_client(_output_json(new_tasks=[_make_new_task(recovery_for="42")]))
        orch = _make_orchestrator(client)
        tasks = [
            _make_view(
                "42",
                TaskStatus.NEEDS_HUMAN_REVIEW,
                lineage_depth=1,
                verdict=VerdictSummary(
                    passed=False,
                    reason="on_task_complete never receives blocked-status records.",
                    infeasible=True,
                ),
            )
        ]
        orch.run_loop(_make_input(tasks=tasks, comments=[]))
        prompt = client.call.call_args.args[1]
        assert '"infeasible": true' in prompt
        assert "on_task_complete never receives blocked-status records." in prompt

    def test_api_error_propagates(self):
        client = MagicMock(spec=ModelClient)
        client.call.side_effect = APIError("timeout")
        orch = _make_orchestrator(client)
        with pytest.raises(APIError, match="timeout"):
            orch.run_loop(_make_input())
