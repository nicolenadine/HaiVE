from __future__ import annotations

from haive.models.config import AgentConfig
from haive.models.context import ContextPack
from haive.models.task import Task


class ContextAssembler:
    def assemble_prompt(
        self,
        task: Task,
        context_pack: ContextPack,
        agent_config: AgentConfig,
        dependency_outputs: dict[str, str],
        retry_feedback: list[str] | None,
    ) -> str:
        sections: list[str] = []

        sections.append(
            f"## Task\n**Title:** {task.title}\n\n{task.description}"
        )

        criteria_lines = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        sections.append(f"## Acceptance Criteria\n{criteria_lines}")

        if context_pack.relevant_symbols:
            code_parts = ["## Relevant Code"]
            for sym in context_pack.relevant_symbols:
                code_parts.append(
                    f"### {sym.file_path} — {sym.qualified_name}\n```python\n{sym.source}\n```"
                )
            sections.append("\n\n".join(code_parts))

        files_lines = "\n".join(
            f"- {f.path} ({f.reason})" for f in context_pack.relevant_files
        )
        sections.append(f"## Relevant Files\n{files_lines}")

        if context_pack.impacted_files:
            impacted_lines = "\n".join(f"- {p}" for p in context_pack.impacted_files)
            sections.append(
                f"## Impacted Files\n"
                f"These files import from the relevant files above and may be affected by changes:\n"
                f"{impacted_lines}"
            )

        if context_pack.broken_references:
            broken_lines = "\n".join(
                f"- {br.file_path}:{br.line_number} references '{br.symbol_name}'"
                for br in context_pack.broken_references
            )
            sections.append(
                f"## Broken References\n"
                f"These symbols are referenced but could not be resolved:\n"
                f"{broken_lines}"
            )

        dep_parts: list[str] = []
        for task_id in task.depends_on:
            output = dependency_outputs.get(task_id)
            if output is not None:
                dep_parts.append(f"### Output from task {task_id}\n{output}")
        if dep_parts:
            sections.append("## Dependency Outputs\n\n" + "\n\n".join(dep_parts))

        if retry_feedback:
            feedback_lines = "\n".join(f"- {item}" for item in retry_feedback)
            sections.append(
                f"## Feedback from Previous Attempt\n"
                f"The following issues were identified in the previous attempt. "
                f"Address each before responding:\n"
                f"{feedback_lines}"
            )

        return "\n\n".join(sections)
