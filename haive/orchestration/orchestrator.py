from __future__ import annotations

from pydantic import ValidationError

from haive.execution.output_validator import OutputValidator
from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.tier_config import TierConfig
from haive.models.orchestrator import OrchestratorInput, OrchestratorOutput
from haive.orchestration.example_library import ExampleLibrary, format_examples_for_prompt
from haive.orchestration.example_selector import ExampleSelector
from haive.orchestration.orchestrator_prompt import build_orchestrator_prompt

_ORCHESTRATOR_MAX_OUTPUT_TOKENS = 4096


class OrchestratorStalledError(RuntimeError):
    """Raised when the orchestrator has no further automatic action to take.

    Distinct from a plain RuntimeError so callers can stop a run loop cleanly
    instead of treating this as a bug — it's a safety mechanism (empty output,
    or a recovery attempt hitting max_recovery_depth) working as designed.
    """

    def __init__(self, message: str, stalled_task_id: str | None = None) -> None:
        super().__init__(message)
        self.stalled_task_id = stalled_task_id


class Orchestrator:
    def __init__(
        self,
        model_client: ModelClient,
        tier_config: TierConfig,
        max_recovery_depth: int,
        max_family_attempts: int,
        example_library: ExampleLibrary | None = None,
    ) -> None:
        self._model_client = model_client
        self._tier_config = tier_config
        self._max_recovery_depth = max_recovery_depth
        self._max_family_attempts = max_family_attempts
        self._example_library = example_library

    def run_loop(self, input: OrchestratorInput) -> OrchestratorOutput:
        prompt = input.model_dump_json(indent=2)

        planning_examples: str | None = None
        if self._example_library is not None:
            milestone_text = f"{input.project.title} {input.project.description}"
            selected = ExampleSelector().select(self._example_library.all(), milestone_text)
            if selected:
                planning_examples = format_examples_for_prompt(selected)

        system = build_orchestrator_prompt(self._max_recovery_depth, planning_examples)

        response = self._model_client.call(
            self._tier_config.orchestrator,
            prompt,
            system,
            max_tokens=_ORCHESTRATOR_MAX_OUTPUT_TOKENS,
        )

        json_str = OutputValidator.extract_json(response.content)
        if json_str is None:
            raise APIError("Could not extract JSON from orchestrator response.")

        try:
            output = OrchestratorOutput.model_validate_json(json_str)
        except ValidationError as e:
            raise RuntimeError(
                f"Orchestrator response failed schema validation: {e}"
            ) from e

        if not output.done and not output.new_tasks:
            raise OrchestratorStalledError(
                "Orchestrator returned empty new_tasks without signaling done. "
                "This is a configuration error — the orchestrator must produce "
                "at least one new task or set done=true."
            )

        task_depth = {view.task_id: view.lineage_depth for view in input.tasks}
        task_by_id = {view.task_id: view for view in input.tasks}
        corrected_new_tasks: list = []
        for new_task in output.new_tasks:
            if new_task.recovery_for is not None:
                source_depth = task_depth.get(new_task.recovery_for, 0)

                # max_recovery_depth bounds lineage *depth*; this bounds total
                # attempts spent across the whole family — tier escalation
                # times attempts times generations can still add up to a lot
                # even within the depth cap. Independent of --unstall: an
                # exemption from the depth limit is not also an exemption
                # from the cost ceiling.
                family_attempts = 0
                walk_id: str | None = new_task.recovery_for
                seen: set[str] = set()
                while walk_id is not None and walk_id not in seen:
                    seen.add(walk_id)
                    ancestor = task_by_id.get(walk_id)
                    if ancestor is None:
                        break
                    family_attempts += len(ancestor.attempt_log)
                    walk_id = ancestor.recovery_for
                if family_attempts > self._max_family_attempts:
                    raise OrchestratorStalledError(
                        f"Recovery task for '{new_task.recovery_for}' would continue a family "
                        f"that has already cost {family_attempts} total attempts, exceeding "
                        f"max_family_attempts ({self._max_family_attempts}).",
                        stalled_task_id=new_task.recovery_for,
                    )

                if new_task.recovery_for == input.unstall_task_id:
                    # A human has explicitly reviewed this specific task and
                    # authorized one recovery attempt beyond wherever its
                    # lineage currently sits (haive run --unstall <task_id>) —
                    # relative to *this task's own depth*, not the configured
                    # max, so a lineage that was already unstalled once can be
                    # unstalled again later. Every other lineage is still held
                    # to max_recovery_depth.
                    effective_max = source_depth + 1
                else:
                    effective_max = self._max_recovery_depth
                if source_depth + 1 > effective_max:
                    raise OrchestratorStalledError(
                        f"Recovery task for '{new_task.recovery_for}' would exceed "
                        f"max_recovery_depth ({self._max_recovery_depth}). "
                        f"Source task lineage_depth={source_depth}.",
                        stalled_task_id=new_task.recovery_for,
                    )
                # Compute lineage_depth authoritatively rather than trusting the
                # orchestrator LLM's own count — a miscount here would silently
                # corrupt the recorded depth for this task and every recovery
                # descendant created from it afterward.
                if new_task.lineage_depth != source_depth + 1:
                    new_task = new_task.model_copy(update={"lineage_depth": source_depth + 1})
            corrected_new_tasks.append(new_task)

        return output.model_copy(update={"new_tasks": corrected_new_tasks})
