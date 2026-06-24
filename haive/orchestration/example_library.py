from __future__ import annotations

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from haive.models.enums import AgentRole, Complexity
from haive.orchestration.example_tags import KNOWN_TAGS


class ExampleTaskPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_role:  AgentRole
    purpose:     str
    complexity:  Complexity
    depends_on:  list[int] = Field(default_factory=list)


class ExampleMiniTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title:      str
    agent_role: AgentRole
    complexity: Complexity
    depends_on: list[int] = Field(default_factory=list)


class ExampleMiniMilestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    milestone:      str
    expected_tasks: list[ExampleMiniTask]


class OrchestratorExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:                   str
    pattern_name:         str
    tags:                 list[str]
    use_when:             list[str]
    do_not_use_when:      list[str] = Field(default_factory=list)
    default_task_graph:   list[ExampleTaskPattern]
    common_wrong_outputs: list[str] = Field(default_factory=list)
    mini_example:         ExampleMiniMilestone | None = None

    @model_validator(mode="after")
    def check_known_tags(self) -> "OrchestratorExample":
        unknown = [t for t in self.tags if t not in KNOWN_TAGS]
        if unknown:
            raise ValueError(
                f"Unknown tag(s) in example '{self.id}': {unknown}. "
                f"Valid tags: {sorted(KNOWN_TAGS)}"
            )
        return self


class OrchestratorExampleLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    examples: list[OrchestratorExample]

    @model_validator(mode="after")
    def check_duplicate_ids(self) -> "OrchestratorExampleLibrary":
        seen: set[str] = set()
        for e in self.examples:
            if e.id in seen:
                raise ValueError(f"Duplicate example ID: '{e.id}'")
            seen.add(e.id)
        return self


class ExampleLibrary:
    def __init__(self, examples: list[OrchestratorExample]) -> None:
        self._examples = examples
        self._by_id = {e.id: e for e in examples}

    @classmethod
    def load(cls, path: str) -> "ExampleLibrary":
        try:
            with open(path) as f:
                raw = yaml.safe_load(f)
        except OSError as e:
            raise RuntimeError(f"Cannot read example library at '{path}': {e}") from e

        if raw is None:
            raise RuntimeError(
                "Example library is empty; expected a root mapping with an 'examples' list."
            )
        if not isinstance(raw, dict):
            raise RuntimeError(
                f"orchestrator_examples.yaml must be a root-level mapping, got {type(raw).__name__}"
            )
        try:
            library = OrchestratorExampleLibrary.model_validate(raw)
        except ValidationError as e:
            raise RuntimeError(f"Invalid example library at '{path}': {e}") from e

        return cls(library.examples)

    def all(self) -> list[OrchestratorExample]:
        return list(self._examples)

    def get(self, example_id: str) -> OrchestratorExample:
        try:
            return self._by_id[example_id]
        except KeyError:
            raise ValueError(f"No example with id '{example_id}'")

    def __len__(self) -> int:
        return len(self._examples)


def format_examples_for_prompt(examples: list[OrchestratorExample]) -> str:
    if not examples:
        return ""

    sections: list[str] = ["## Relevant planning examples"]

    for ex in examples:
        lines: list[str] = [f"\n### {ex.pattern_name}"]

        lines.append("Use when:")
        for item in ex.use_when:
            lines.append(f"- {item}")

        if ex.do_not_use_when:
            lines.append("Do not use when:")
            for item in ex.do_not_use_when:
                lines.append(f"- {item}")

        lines.append("\nPattern:")
        for i, step in enumerate(ex.default_task_graph):
            if step.depends_on:
                dep_labels = ", ".join(f"step {d + 1}" for d in step.depends_on)
                dep_str = f"; depends on {dep_labels}"
            else:
                dep_str = ""
            lines.append(
                f"{i + 1}. {step.agent_role.value} ({step.complexity.value}): {step.purpose}{dep_str}"
            )

        if ex.common_wrong_outputs:
            lines.append("\nAvoid:")
            for item in ex.common_wrong_outputs:
                lines.append(f"- {item}")

        if ex.mini_example:
            me = ex.mini_example
            lines.append(f'\nExample: "{me.milestone}"')
            for i, t in enumerate(me.expected_tasks):
                if t.depends_on:
                    dep_labels = ", ".join(str(d + 1) for d in t.depends_on)
                    dep_str = f"  [depends: {dep_labels}]"
                else:
                    dep_str = ""
                lines.append(f"  {i + 1}. {t.agent_role.value}: {t.title}{dep_str}")

        sections.append("\n".join(lines))

    return "\n".join(sections)
