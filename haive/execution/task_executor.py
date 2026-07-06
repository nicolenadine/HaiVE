from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from haive.adapters.pm.base import PMAdapter
from haive.adapters.vcs.base import VCSAdapter
from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
from haive.discovery.file_index_service import FileIndexService
from haive.execution.context_assembler import ContextAssembler
from haive.execution.output_validator import OutputValidationError, OutputValidator
from haive.execution.review_agent import ReviewAgent
from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.llm.tier_config import TierConfig
from haive.models.agent_output import ScaffoldAgentOutput
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.review import ReviewVerdict
from haive.models.state import ProjectState
from haive.models.task import AttemptLogEntry, Task, TaskExecutionRecord
from haive.observability.spans import task_span
from haive.persistence.state_store import StateStore
from haive.registry.agent_registry import AgentRegistry

_SCAFFOLD_ROLES: frozenset[AgentRole] = frozenset({AgentRole.SCAFFOLD_AGENT})
_MAX_API_ERRORS = 3


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TaskExecutor:
    """Executes a single task end-to-end: branch → LLM → review → PR → merge.

    Constructor takes stable per-project state; run() takes per-task inputs.
    """

    def __init__(
        self,
        model_client: ModelClient,
        tier_config: TierConfig,
        review_agent: ReviewAgent,
        root: str,
        project_branch: str,
        auto_merge: bool = True,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._model_client = model_client
        self._tier_config = tier_config
        self._review_agent = review_agent
        self._root = root
        self._project_branch = project_branch
        self._auto_merge = auto_merge
        self._on_status = on_status or (lambda _: None)
        self._validator = OutputValidator()
        self._assembler = ContextAssembler()
        # Set once a merge fails with the repo-wide "not allowed" error, so
        # subsequent tasks in this run skip repeating a call already known
        # to fail, rather than piling up many independently-stuck PRs.
        self._auto_merge_disabled_this_run = False

    def run(
        self,
        task: Task,
        project_id: str,
        project_state: ProjectState,
        discovery_agent: CodeDiscoveryAgent,
        file_index: FileIndexService,
        registry: AgentRegistry,
        pm: PMAdapter,
        vcs: VCSAdapter,
        state_store: StateStore,
    ) -> TaskExecutionRecord:
        with task_span(task) as span:
            record = self._run_inner(
                task, project_id, project_state,
                discovery_agent, file_index, registry, pm, vcs, state_store,
            )
            if record.verdict is not None:
                span.set_attribute("verdict.passed", record.verdict.passed)
            if record.prompt_version is not None:
                span.set_attribute("agent.prompt_version", record.prompt_version)
            if record.tier_used is not None:
                span.set_attribute("tier.name", record.tier_used.value)
            if record.model_used is not None:
                span.set_attribute("tier.model_used", record.model_used)
            span.set_attribute("attempt.number", record.total_attempts)
        return record

    def _run_inner(
        self,
        task: Task,
        project_id: str,
        project_state: ProjectState,
        discovery_agent: CodeDiscoveryAgent,
        file_index: FileIndexService,
        registry: AgentRegistry,
        pm: PMAdapter,
        vcs: VCSAdapter,
        state_store: StateStore,
    ) -> TaskExecutionRecord:
        record = TaskExecutionRecord(task_id=task.task_id, executor_start=_utcnow())
        attempt_num = 0
        retry_feedback: list[str] = []

        pm.update_status(task.task_id, TaskStatus.IN_PROGRESS)

        agent_config = registry.get_agent(task.agent_role)
        system_prompt = Path(self._root, agent_config.system_prompt).read_text(encoding="utf-8")
        dependency_outputs = self._build_dependency_outputs(task, project_state)
        task_branch = f"haive/task-{task.task_id}"

        self._on_status(f"  [#{task.task_id}] {task.title}  [{task.agent_role.value} / {task.complexity.value}]")
        self._on_status(f"  [#{task.task_id}] creating branch {task_branch}")
        vcs.create_branch(task_branch, self._project_branch)

        for complexity, tier in self._get_tier_ladder(task.complexity):
            token_budget = int(tier.context_budget * agent_config.context_budget_multiplier)
            self._on_status(f"  [#{task.task_id}] discovering context  [tier={complexity.value}, budget={token_budget:,}]")
            discovery_result = discovery_agent.discover(task, self._root, token_budget)
            loaded_sections = file_index.load_sections(discovery_result, self._root, token_budget)
            self._on_status(f"  [#{task.task_id}] loaded {len(loaded_sections)} section(s)")
            discovery_status = self._compute_discovery_status(discovery_result, task.agent_role)
            discovery_note = (
                "No existing code found for this task."
                if discovery_status == "empty_unexpected"
                else ""
            )
            consecutive_api_errors = 0

            for _ in range(tier.max_attempts):
                context = self._assembler.assemble(
                    task=task,
                    loaded_sections=loaded_sections,
                    discovery_status=discovery_status,
                    dependency_outputs=dependency_outputs,
                    retry_feedback=retry_feedback or None,
                )

                self._on_status(f"  [#{task.task_id}] LLM call  [attempt={attempt_num + 1}, tier={complexity.value}]")
                try:
                    response = self._model_client.call(
                        tier, context, system_prompt, agent_config.max_tokens
                    )
                    consecutive_api_errors = 0
                except APIError as exc:
                    consecutive_api_errors += 1
                    self._on_status(f"  [#{task.task_id}] API error (attempt not counted): {exc}")
                    record.attempt_log.append(
                        AttemptLogEntry(
                            tier=complexity,
                            attempt=attempt_num,
                            reason=f"API error: {exc}",
                        )
                    )
                    if consecutive_api_errors >= _MAX_API_ERRORS:
                        raise
                    continue

                attempt_num += 1

                try:
                    agent_output = self._validator.validate(response.content, task.agent_role)
                except OutputValidationError as exc:
                    self._on_status(f"  [#{task.task_id}] schema validation failed — retrying")
                    record.attempt_log.append(
                        AttemptLogEntry(
                            tier=complexity,
                            attempt=attempt_num,
                            reason=f"Schema: {exc}",
                        )
                    )
                    retry_feedback = [str(exc)]
                    continue

                self._on_status(f"  [#{task.task_id}] reviewing output  [{response.model_used}]")
                verdict = self._review_agent.review(
                    task=task,
                    agent_output=agent_output,
                    loaded_sections=loaded_sections,
                    discovery_status=discovery_status,
                    discovery_note=discovery_note,
                )

                if verdict.passed:
                    self._on_status(f"  [#{task.task_id}] review passed — applying output")
                    return self._finalize_success(
                        task=task,
                        project_id=project_id,
                        record=record,
                        agent_output=agent_output,
                        verdict=verdict,
                        task_branch=task_branch,
                        attempt_num=attempt_num,
                        complexity=complexity,
                        response_model=response.model_used,
                        prompt_version=agent_config.prompt_version,
                        file_index=file_index,
                        pm=pm,
                        vcs=vcs,
                        state_store=state_store,
                    )

                if verdict.infeasible:
                    self._on_status(f"  [#{task.task_id}] acceptance criteria infeasible — {verdict.reason}")
                    record.attempt_log.append(
                        AttemptLogEntry(
                            tier=complexity,
                            attempt=attempt_num,
                            reason=verdict.reason,
                        )
                    )
                    record.verdict = verdict.to_summary()
                    pm.add_comment(task.task_id, _format_infeasible_summary(verdict.reason))
                    pm.update_status(task.task_id, TaskStatus.NEEDS_HUMAN_REVIEW)
                    record.total_attempts = attempt_num
                    record.executor_end = _utcnow()
                    state_store.merge_task_record(project_id, task.task_id, record)
                    return record

                self._on_status(f"  [#{task.task_id}] review failed — {verdict.reason}")
                if verdict.suggestions:
                    for suggestion in verdict.suggestions:
                        self._on_status(f"  [#{task.task_id}]   suggestion: {suggestion}")
                record.attempt_log.append(
                    AttemptLogEntry(
                        tier=complexity,
                        attempt=attempt_num,
                        reason=verdict.reason,
                    )
                )
                retry_feedback = verdict.suggestions

        # All tiers exhausted
        self._on_status(f"  [#{task.task_id}] all tiers exhausted — needs human review")
        pm.add_comment(task.task_id, _format_attempt_summary(record.attempt_log))
        pm.update_status(task.task_id, TaskStatus.NEEDS_HUMAN_REVIEW)
        record.total_attempts = attempt_num
        record.executor_end = _utcnow()
        state_store.merge_task_record(project_id, task.task_id, record)
        return record

    # ── private helpers ───────────────────────────────────────────────────────

    def _finalize_success(
        self,
        task: Task,
        project_id: str,
        record: TaskExecutionRecord,
        agent_output: object,
        verdict: ReviewVerdict,
        task_branch: str,
        attempt_num: int,
        complexity: Complexity,
        response_model: str,
        prompt_version: str,
        file_index: FileIndexService,
        pm: PMAdapter,
        vcs: VCSAdapter,
        state_store: StateStore,
    ) -> TaskExecutionRecord:
        # create_branch() already checked the local working directory out onto
        # task_branch (in _run_inner, before this method runs). Everything below
        # can fail in ways we don't otherwise handle (network hiccups, GitHub API
        # errors) — the finally block guarantees the local repo always gets back
        # to project_branch, so a failure here never leaves it stuck on a task
        # branch for the next run to trip over.
        try:
            task_changed_files = _apply_output(agent_output, self._root)
            agent_md_touched = file_index.update_after_task(task_changed_files, self._root)
            changed_files = sorted(set(task_changed_files) | set(agent_md_touched))
            self._on_status(f"  [#{task.task_id}] pushing {len(changed_files)} file(s): {', '.join(changed_files)}")
            vcs.push_commits(
                task_branch,
                changed_files,
                f"haive: {task.task_id} {task.title}",
            )
            pr_id = vcs.create_pr(
                f"Task {task.task_id}: {task.title}",
                verdict.reason,
                task_branch,
                self._project_branch,
            )
            self._on_status(f"  [#{task.task_id}] PR created: #{pr_id}" + ("" if self._auto_merge else " (not auto-merged)"))
            vcs.add_pr_comment(pr_id, _format_pr_comment(record.attempt_log, verdict))

            if self._auto_merge:
                if self._auto_merge_disabled_this_run:
                    merged = False
                    merge_exc_text = "auto-merge disabled for this run (repository does not support it)"
                else:
                    try:
                        vcs.merge_pr(pr_id)
                        merged, merge_exc_text = True, None
                    except RuntimeError as exc:
                        merged, merge_exc_text = False, str(exc)
                        if "Auto merge is not allowed for this repository" in merge_exc_text:
                            self._auto_merge_disabled_this_run = True

                if merged:
                    pm.update_status(task.task_id, TaskStatus.COMPLETE)
                else:
                    self._on_status(f"  [#{task.task_id}] auto-merge failed — leaving PR #{pr_id} open: {merge_exc_text}")
                    note = _format_merge_failure_note(pr_id, merge_exc_text)
                    vcs.add_pr_comment(pr_id, note)
                    pm.add_comment(task.task_id, note)
                    pm.update_status(task.task_id, TaskStatus.AWAITING_MERGE)
            else:
                merged = True  # --no-merge: deliberate, unchanged — still marks complete
                pm.update_status(task.task_id, TaskStatus.COMPLETE)
        finally:
            vcs.checkout_branch(self._project_branch)

        now = _utcnow()
        record.verdict = verdict.to_summary()
        record.pr_id = pr_id
        record.merged = merged
        record.changed_files = changed_files
        record.model_used = response_model
        record.tier_used = complexity
        record.total_attempts = attempt_num
        record.prompt_version = prompt_version
        record.completed_at = now
        record.executor_end = now
        state_store.merge_task_record(project_id, task.task_id, record)
        return record

    def _get_tier_ladder(self, complexity: Complexity) -> list[tuple[Complexity, Tier]]:
        full: list[tuple[Complexity, Tier]] = [
            (Complexity.LOW, self._tier_config.low),
            (Complexity.MEDIUM, self._tier_config.medium),
            (Complexity.HIGH, self._tier_config.high),
        ]
        start = next(i for i, (c, _) in enumerate(full) if c == complexity)
        return full[start:]

    @staticmethod
    def _compute_discovery_status(
        result: object,
        role: AgentRole,
    ) -> Literal["found", "empty_expected", "empty_unexpected"]:
        if result.sections:  # type: ignore[attr-defined]
            return "found"
        if role in _SCAFFOLD_ROLES:
            return "empty_expected"
        return "empty_unexpected"

    @staticmethod
    def _build_dependency_outputs(task: Task, project_state: ProjectState) -> dict[str, str]:
        outputs: dict[str, str] = {}
        for dep_id in task.depends_on:
            dep_record = project_state.tasks.get(dep_id)
            if dep_record and dep_record.verdict:
                parts = [
                    f"Status: {'passed' if dep_record.verdict.passed else 'failed'}",
                    f"Summary: {dep_record.verdict.reason}",
                ]
                if dep_record.changed_files:
                    parts.append(f"Changed files: {', '.join(dep_record.changed_files)}")
                outputs[dep_id] = "\n".join(parts)
        return outputs


# ── module-level helpers ──────────────────────────────────────────────────────

def _apply_output(agent_output: object, root: str) -> list[str]:
    if isinstance(agent_output, ScaffoldAgentOutput):
        items = [(f.path, f.content) for f in agent_output.files]
    else:
        items = [(e.path, e.content) for e in agent_output.edits]  # type: ignore[attr-defined]
    for path_str, content in items:
        p = Path(root) / path_str
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return [path_str for path_str, _ in items]


def _format_attempt_summary(attempt_log: list[AttemptLogEntry]) -> str:
    lines = ["**haive: all attempts exhausted — needs human review**", ""]
    for entry in attempt_log:
        lines.append(f"- Tier {entry.tier.value}, attempt {entry.attempt}: {entry.reason}")
    return "\n".join(lines)


def _format_infeasible_summary(reason: str) -> str:
    return (
        "**haive: acceptance criteria are architecturally infeasible**\n\n"
        "The reviewer determined this task's acceptance criteria cannot be satisfied by any "
        "implementation, given the current code architecture — this is not an implementation "
        "mistake. The task's scope or acceptance criteria need to be revised.\n\n"
        f"Reviewer's reasoning: {reason}"
    )


def _format_pr_comment(
    attempt_log: list[AttemptLogEntry],
    verdict: ReviewVerdict,
) -> str:
    lines = [f"**haive review:** {verdict.reason}"]
    if len(attempt_log) > 1:
        lines.append("")
        lines.append(f"Completed after {len(attempt_log)} attempt(s).")
    return "\n".join(lines)


def _format_merge_failure_note(pr_id: str, reason: str) -> str:
    return (
        f"**haive: auto-merge failed for PR #{pr_id}**\n\n"
        "This task already passed review — the code is correct, only the merge step failed. "
        "No rewrite is needed; merge the PR manually to complete this task.\n\n"
        f"Reason: {reason}"
    )
