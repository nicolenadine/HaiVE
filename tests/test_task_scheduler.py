from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from haive.adapters.pm.base import PMAdapter
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task, TaskExecutionRecord, VerdictSummary
from haive.orchestration.task_scheduler import MAX_EXECUTORS, TaskScheduler


# ── fixtures ──────────────────────────────────────────────────────────────────

def make_task(task_id: str, *, depends_on: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        title=f"Task {task_id}",
        description="Test task.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.LOW,
        depends_on=depends_on or [],
        acceptance_criteria=[],
        status=TaskStatus.PENDING,
    )


def make_record(task_id: str, *, passed: bool = True) -> TaskExecutionRecord:
    return TaskExecutionRecord(
        task_id=task_id,
        verdict=VerdictSummary(passed=passed, reason="done") if passed else None,
    )


def passing_factory(task: Task) -> TaskExecutionRecord:
    return make_record(task.task_id, passed=True)


def failing_factory(task: Task) -> TaskExecutionRecord:
    return make_record(task.task_id, passed=False)


# ── concurrency cap ───────────────────────────────────────────────────────────

class TestConcurrencyCap:
    def test_at_most_max_executors_run_simultaneously(self):
        active = 0
        max_active = 0
        lock = threading.Lock()

        def factory(task: Task) -> TaskExecutionRecord:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return make_record(task.task_id)

        tasks = [make_task(str(i)) for i in range(5)]
        TaskScheduler().start(tasks, factory, pm=MagicMock(spec=PMAdapter))

        assert max_active <= MAX_EXECUTORS

    def test_all_independent_tasks_eventually_complete(self):
        completed: list[str] = []

        def factory(task: Task) -> TaskExecutionRecord:
            completed.append(task.task_id)
            return make_record(task.task_id)

        tasks = [make_task(str(i)) for i in range(5)]
        TaskScheduler().start(tasks, factory, pm=MagicMock(spec=PMAdapter))

        assert sorted(completed) == ["0", "1", "2", "3", "4"]


# ── dependency ordering ───────────────────────────────────────────────────────

class TestDependencyOrdering:
    def test_dependent_task_runs_after_dependency_completes(self):
        order: list[str] = []

        def factory(task: Task) -> TaskExecutionRecord:
            order.append(task.task_id)
            return make_record(task.task_id, passed=True)

        task_a = make_task("A")
        task_b = make_task("B", depends_on=["A"])
        TaskScheduler().start([task_a, task_b], factory, pm=MagicMock(spec=PMAdapter))

        assert order.index("A") < order.index("B")

    def test_chain_completes_in_order(self):
        order: list[str] = []

        def factory(task: Task) -> TaskExecutionRecord:
            order.append(task.task_id)
            return make_record(task.task_id, passed=True)

        task_a = make_task("A")
        task_b = make_task("B", depends_on=["A"])
        task_c = make_task("C", depends_on=["B"])
        TaskScheduler().start([task_a, task_b, task_c], factory, pm=MagicMock(spec=PMAdapter))

        assert order == ["A", "B", "C"]

    def test_independent_tasks_run_in_parallel_with_chain(self):
        started: list[str] = []
        barrier = threading.Barrier(2, timeout=2.0)

        def factory(task: Task) -> TaskExecutionRecord:
            started.append(task.task_id)
            if task.task_id in ("A", "X"):
                barrier.wait()  # both should be running concurrently
            return make_record(task.task_id, passed=True)

        task_a = make_task("A")
        task_x = make_task("X")
        task_b = make_task("B", depends_on=["A"])
        TaskScheduler().start([task_a, task_b, task_x], factory, pm=MagicMock(spec=PMAdapter))

        assert "A" in started
        assert "X" in started
        assert "B" in started


# ── blocked propagation ───────────────────────────────────────────────────────

class TestBlockedPropagation:
    def test_dependent_task_blocked_when_dependency_fails(self):
        executed: list[str] = []
        pm = MagicMock(spec=PMAdapter)

        def factory(task: Task) -> TaskExecutionRecord:
            executed.append(task.task_id)
            return make_record(task.task_id, passed=False)

        task_a = make_task("A")
        task_b = make_task("B", depends_on=["A"])
        TaskScheduler().start([task_a, task_b], factory, pm=pm)

        assert "B" not in executed
        pm.update_status.assert_called_with("B", TaskStatus.BLOCKED)

    def test_blocked_propagates_transitively(self):
        executed: list[str] = []
        pm = MagicMock(spec=PMAdapter)

        def factory(task: Task) -> TaskExecutionRecord:
            executed.append(task.task_id)
            return make_record(task.task_id, passed=False)

        task_a = make_task("A")
        task_b = make_task("B", depends_on=["A"])
        task_c = make_task("C", depends_on=["B"])
        TaskScheduler().start([task_a, task_b, task_c], factory, pm=pm)

        assert "B" not in executed
        assert "C" not in executed
        blocked_ids = {call.args[0] for call in pm.update_status.call_args_list
                       if call.args[1] == TaskStatus.BLOCKED}
        assert "B" in blocked_ids
        assert "C" in blocked_ids

    def test_independent_tasks_continue_after_failure(self):
        executed: list[str] = []
        pm = MagicMock(spec=PMAdapter)

        def factory(task: Task) -> TaskExecutionRecord:
            executed.append(task.task_id)
            passed = task.task_id != "A"
            return make_record(task.task_id, passed=passed)

        task_a = make_task("A")
        task_b = make_task("B", depends_on=["A"])
        task_x = make_task("X")  # independent
        TaskScheduler().start([task_a, task_b, task_x], factory, pm=pm)

        assert "A" in executed
        assert "X" in executed
        assert "B" not in executed


# ── already-complete tasks ────────────────────────────────────────────────────

class TestNonPendingTasks:
    def test_complete_task_not_re_executed(self):
        executed: list[str] = []

        def factory(task: Task) -> TaskExecutionRecord:
            executed.append(task.task_id)
            return make_record(task.task_id)

        complete_task = Task(
            task_id="done",
            title="Already done",
            description="",
            agent_role=AgentRole.IMPLEMENTATION_AGENT,
            complexity=Complexity.LOW,
            depends_on=[],
            acceptance_criteria=[],
            status=TaskStatus.COMPLETE,
        )
        pending_task = make_task("new")
        TaskScheduler().start([complete_task, pending_task], factory, pm=MagicMock(spec=PMAdapter))

        assert "done" not in executed
        assert "new" in executed

    def test_pending_task_with_complete_dep_starts_immediately(self):
        executed: list[str] = []

        def factory(task: Task) -> TaskExecutionRecord:
            executed.append(task.task_id)
            return make_record(task.task_id)

        complete_task = Task(
            task_id="dep",
            title="Dep",
            description="",
            agent_role=AgentRole.IMPLEMENTATION_AGENT,
            complexity=Complexity.LOW,
            depends_on=[],
            acceptance_criteria=[],
            status=TaskStatus.COMPLETE,
        )
        pending_task = make_task("child", depends_on=["dep"])
        TaskScheduler().start([complete_task, pending_task], factory, pm=MagicMock(spec=PMAdapter))

        assert "child" in executed
