from __future__ import annotations

import re

from pydantic import ValidationError

from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.tier_config import TierConfig
from haive.models.orchestrator import OrchestratorInput, OrchestratorOutput

_ORCHESTRATOR_MAX_OUTPUT_TOKENS = 4096


def _extract_json(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{"):
        return stripped
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
    if m:
        return m.group(1).strip()
    raise APIError("Could not extract JSON from orchestrator response.")


def _build_system_prompt(max_recovery_depth: int) -> str:
    return f"""You are the orchestrator for an AI-driven software development workflow.
On each run you receive a snapshot of the project and produce the next batch of tasks to create,
or signal that the project is complete.

## Input

You receive a JSON object with these fields:
- project: project metadata (id, title, description, branch)
- tasks: list of existing tasks, each with id, title, description, agent_role, complexity,
  depends_on, lineage_depth, recovery_for, status, verdict, and attempt_log
- new_comments: list of new human comments since the last run (task_id, author, body, created_at)
- agent_summary: one-line description per available agent role

## Output

Respond with pure JSON only. No markdown, no explanation. Schema:

{{
  "new_tasks": [
    {{
      "title": "...",
      "description": "...",
      "agent_role": "<role>",
      "complexity": "low" | "medium" | "high",
      "depends_on": [...],
      "acceptance_criteria": ["..."],
      "recovery_for": null | "<task_id>",
      "lineage_depth": 0
    }}
  ],
  "done": false
}}

## depends_on formats

Each entry in depends_on is a string in one of two formats:
- "42" — the GitHub issue number of an existing task
- "new:0", "new:1" — zero-based index into the current new_tasks list (resolved to real issue numbers during task creation)

Use intra-wave refs ("new:N") when a task in this wave depends on another task in the same wave.

## Recovery rules

If a task has status "needs_human_review" AND its task_id appears in new_comments AND
lineage_depth < {max_recovery_depth}:
- Create a recovery NewTask with recovery_for set to the failed task's task_id
- Set lineage_depth = failed_task.lineage_depth + 1

Never create a recovery task if lineage_depth >= {max_recovery_depth}.

## Done condition

Set done=true only when every task has status "complete" and no pending, blocked, or
in_progress tasks remain. new_tasks must be empty when done=true.

## Prohibitions

Do not include model names, file paths, or implementation code in task titles or descriptions.
Tasks describe WHAT to do, not HOW. Keep descriptions concise and implementation-agnostic."""


class Orchestrator:
    def __init__(
        self,
        model_client: ModelClient,
        tier_config: TierConfig,
        max_recovery_depth: int,
    ) -> None:
        self._model_client = model_client
        self._tier_config = tier_config
        self._max_recovery_depth = max_recovery_depth

    def run_loop(self, input: OrchestratorInput) -> OrchestratorOutput:
        prompt = input.model_dump_json(indent=2)
        system = _build_system_prompt(self._max_recovery_depth)

        response = self._model_client.call(
            self._tier_config.orchestrator,
            prompt,
            system,
            max_tokens=_ORCHESTRATOR_MAX_OUTPUT_TOKENS,
        )

        json_str = _extract_json(response.content)

        try:
            output = OrchestratorOutput.model_validate_json(json_str)
        except ValidationError as e:
            raise RuntimeError(
                f"Orchestrator response failed schema validation: {e}"
            ) from e

        if not output.done and not output.new_tasks:
            raise RuntimeError(
                "Orchestrator returned empty new_tasks without signaling done. "
                "This is a configuration error — the orchestrator must produce "
                "at least one new task or set done=true."
            )

        task_depth = {view.task_id: view.lineage_depth for view in input.tasks}
        for new_task in output.new_tasks:
            if new_task.recovery_for is not None:
                source_depth = task_depth.get(new_task.recovery_for, 0)
                if source_depth + 1 > self._max_recovery_depth:
                    raise RuntimeError(
                        f"Recovery task for '{new_task.recovery_for}' would exceed "
                        f"max_recovery_depth ({self._max_recovery_depth}). "
                        f"Source task lineage_depth={source_depth}."
                    )

        return output
