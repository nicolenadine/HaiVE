from __future__ import annotations

import json

from haive.llm.token_counter import TokenCounter
from haive.models.enums import TaskStatus
from haive.models.orchestrator import OrchestratorTaskView
from haive.models.state import ProjectState
from haive.models.task import Task


class TaskViewBuilder:
    def build(
        self,
        tasks: list[Task],
        local_state: ProjectState,
        budget_tokens: int,
    ) -> list[OrchestratorTaskView]:
        views: list[OrchestratorTaskView] = []
        for task in tasks:
            record = local_state.tasks.get(task.task_id)
            verdict = record.verdict if record else None
            attempt_log = (
                record.attempt_log
                if record and task.status != TaskStatus.COMPLETE
                else []
            )
            views.append(
                OrchestratorTaskView(
                    task_id=task.task_id,
                    title=task.title,
                    description=task.description,
                    agent_role=task.agent_role,
                    complexity=task.complexity,
                    depends_on=task.depends_on,
                    lineage_depth=task.lineage_depth,
                    recovery_for=task.recovery_for,
                    status=task.status,
                    verdict=verdict,
                    attempt_log=attempt_log,
                )
            )

        total = TokenCounter.estimate(
            json.dumps([v.model_dump(mode="json") for v in views])
        )
        if total > budget_tokens:
            complete = sorted(
                [v for v in views if v.status == TaskStatus.COMPLETE],
                key=lambda v: int(v.task_id) if v.task_id.isdigit() else 0,
            )
            for old_view in complete:
                if total <= budget_tokens:
                    break
                views.remove(old_view)
                total = TokenCounter.estimate(
                    json.dumps([v.model_dump(mode="json") for v in views])
                )

        return views
