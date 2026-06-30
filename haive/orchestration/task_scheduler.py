from __future__ import annotations

import asyncio
from collections.abc import Callable

from haive.adapters.pm.base import PMAdapter
from haive.models.enums import TaskStatus
from haive.models.task import Task, TaskExecutionRecord

MAX_EXECUTORS = 2


class TaskScheduler:
    """Schedules concurrent task execution respecting dependency ordering.

    Maintains a local status map to drive scheduling decisions — task status
    is authoritative inside this class once start() is running. The executor
    (or factory) is responsible for updating PM and StateStore; the scheduler
    only calls pm.update_status() for BLOCKED transitions it decides.

    Usage::

        factory = lambda task: executor.run(task, project_id, state_store.load_or_init(project_id), ...)
        scheduler = TaskScheduler()
        scheduler.start(tasks, factory, pm=pm_adapter)
    """

    def start(
        self,
        tasks: list[Task],
        executor_factory: Callable[[Task], TaskExecutionRecord],
        pm: PMAdapter,
        on_complete: Callable[[TaskExecutionRecord], None] | None = None,
    ) -> None:
        asyncio.run(self._run(tasks, executor_factory, pm, on_complete))

    # ── async core ────────────────────────────────────────────────────────────

    async def _run(
        self,
        tasks: list[Task],
        executor_factory: Callable[[Task], TaskExecutionRecord],
        pm: PMAdapter,
        on_complete: Callable[[TaskExecutionRecord], None] | None = None,
    ) -> None:
        statuses: dict[str, TaskStatus] = {t.task_id: t.status for t in tasks}
        task_map: dict[str, Task] = {t.task_id: t for t in tasks}
        unscheduled: dict[str, Task] = {
            t.task_id: t for t in tasks if t.status == TaskStatus.PENDING
        }
        running: set[asyncio.Task[TaskExecutionRecord]] = set()
        semaphore = asyncio.Semaphore(MAX_EXECUTORS)

        while unscheduled or running:
            ready = [t for t in unscheduled.values() if self._is_ready(t, statuses)]
            for task in ready:
                del unscheduled[task.task_id]
                running.add(
                    asyncio.create_task(
                        self._execute(task, semaphore, executor_factory),
                        name=f"task-{task.task_id}",
                    )
                )

            if not running:
                break

            done, running = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)

            for future in done:
                record: TaskExecutionRecord = await future
                new_status = self._status_from_record(record)
                statuses[record.task_id] = new_status

                if on_complete is not None:
                    on_complete(record)

                if new_status == TaskStatus.NEEDS_HUMAN_REVIEW:
                    self._mark_blocked_downstream(
                        record.task_id, task_map, statuses, unscheduled, pm
                    )

    async def _execute(
        self,
        task: Task,
        semaphore: asyncio.Semaphore,
        executor_factory: Callable[[Task], TaskExecutionRecord],
    ) -> TaskExecutionRecord:
        async with semaphore:
            return await asyncio.to_thread(executor_factory, task)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_ready(task: Task, statuses: dict[str, TaskStatus]) -> bool:
        if statuses.get(task.task_id) != TaskStatus.PENDING:
            return False
        return all(statuses.get(dep_id) == TaskStatus.COMPLETE for dep_id in task.depends_on)

    @staticmethod
    def _status_from_record(record: TaskExecutionRecord) -> TaskStatus:
        if record.verdict is not None and record.verdict.passed:
            return TaskStatus.COMPLETE
        return TaskStatus.NEEDS_HUMAN_REVIEW

    def _mark_blocked_downstream(
        self,
        failed_id: str,
        task_map: dict[str, Task],
        statuses: dict[str, TaskStatus],
        unscheduled: dict[str, Task],
        pm: PMAdapter,
    ) -> None:
        for task in task_map.values():
            if (
                failed_id in task.depends_on
                and statuses.get(task.task_id) == TaskStatus.PENDING
            ):
                statuses[task.task_id] = TaskStatus.BLOCKED
                unscheduled.pop(task.task_id, None)
                pm.update_status(task.task_id, TaskStatus.BLOCKED)
                self._mark_blocked_downstream(task.task_id, task_map, statuses, unscheduled, pm)
