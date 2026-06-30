from __future__ import annotations

from typing import Literal

from haive.models.config import AgentConfig
from haive.models.discovery import LoadedSection
from haive.models.task import Task


class ContextAssembler:
    """Assembles the final agent prompt from pre-loaded context pieces.

    No I/O or service calls — all file content has already been loaded by
    FileIndexService. Assembly order:
      1. System prompt (from AgentConfig)
      2. Task description and acceptance criteria
      3. Discovered source sections (or an explicit no-context note)
      4. Dependency outputs
      5. Retry feedback (only on retries)
    """

    def assemble(
        self,
        task: Task,
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
        agent_config: AgentConfig,
        dependency_outputs: dict[str, str],
        retry_feedback: list[str] | None = None,
    ) -> str:
        parts: list[str] = []

        parts.append(agent_config.system_prompt.strip())

        parts.append(self._task_section(task))

        parts.append(self._context_section(loaded_sections, discovery_status))

        if dependency_outputs:
            parts.append(self._dependency_section(dependency_outputs))

        if retry_feedback:
            parts.append(self._feedback_section(retry_feedback))

        return "\n\n".join(parts)

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _task_section(task: Task) -> str:
        lines = [
            "## Task",
            "",
            f"**{task.title}**",
            "",
            task.description.strip(),
        ]
        if task.acceptance_criteria:
            lines.append("")
            lines.append("**Acceptance criteria:**")
            for criterion in task.acceptance_criteria:
                lines.append(f"- {criterion}")
        return "\n".join(lines)

    @staticmethod
    def _context_section(
        loaded_sections: list[LoadedSection],
        discovery_status: Literal["found", "empty_expected", "empty_unexpected"],
    ) -> str:
        if not loaded_sections:
            if discovery_status == "empty_expected":
                note = (
                    "No existing relevant code was found for this task. "
                    "This is expected — you are creating new code from scratch."
                )
            else:
                note = (
                    "No existing relevant code was found for this task. "
                    "Proceed based on the task description alone."
                )
            return f"## Relevant Code\n\n{note}"

        section_blocks = ["## Relevant Code"]
        for s in loaded_sections:
            section_blocks.append(f"### {s.file}\n\n{s.reason}\n\n```\n{s.source.rstrip()}\n```")
        return "\n\n".join(section_blocks)

    @staticmethod
    def _dependency_section(dependency_outputs: dict[str, str]) -> str:
        blocks = ["## Dependency Outputs"]
        for task_id, output in dependency_outputs.items():
            blocks.append(f"### Task {task_id}\n\n{output.strip()}")
        return "\n\n".join(blocks)

    @staticmethod
    def _feedback_section(retry_feedback: list[str]) -> str:
        lines = ["## Reviewer Feedback", ""]
        lines.append("Address the following issues from the previous attempt:")
        for item in retry_feedback:
            lines.append(f"- {item}")
        return "\n".join(lines)
