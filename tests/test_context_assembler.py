from __future__ import annotations

import pytest

from haive.execution.context_assembler import ContextAssembler
from haive.models.config import AgentConfig
from haive.models.discovery import LoadedSection
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task


# ── fixtures ──────────────────────────────────────────────────────────────────

def make_task(**kwargs) -> Task:
    defaults = dict(
        task_id="42",
        title="Add retry logic",
        description="Wrap the HTTP client with exponential backoff.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.LOW,
        depends_on=[],
        acceptance_criteria=["retries on 5xx", "max 3 attempts"],
        status=TaskStatus.IN_PROGRESS,
    )
    return Task(**(defaults | kwargs))


def make_agent_config(**kwargs) -> AgentConfig:
    defaults = dict(
        role=AgentRole.IMPLEMENTATION_AGENT,
        description="Writes implementation code.",
        skills=["python"],
        system_prompt="You are an implementation agent. Write clean, tested code.",
        output_schema="CodeEditorOutput",
        max_tokens=4096,
        retry_limit=2,
        prompt_version="v1",
    )
    return AgentConfig(**(defaults | kwargs))


def make_section(file: str, source: str, reason: str = "Relevant to task.") -> LoadedSection:
    return LoadedSection(file=file, source=source, reason=reason)


# ── section order ─────────────────────────────────────────────────────────────

class TestAssemblyOrder:
    def test_system_prompt_appears_first(self):
        assembler = ContextAssembler()
        config = make_agent_config(system_prompt="SYSTEM PROMPT SENTINEL")
        result = assembler.assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=config,
            dependency_outputs={},
        )
        assert result.startswith("SYSTEM PROMPT SENTINEL")

    def test_task_section_follows_system_prompt(self):
        assembler = ContextAssembler()
        config = make_agent_config(system_prompt="SYS")
        result = assembler.assemble(
            task=make_task(title="My Task"),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=config,
            dependency_outputs={},
        )
        sys_pos = result.index("SYS")
        task_pos = result.index("My Task")
        assert sys_pos < task_pos

    def test_context_follows_task(self):
        assembler = ContextAssembler()
        section = make_section("haive/client.py", "class Client: pass")
        result = assembler.assemble(
            task=make_task(title="My Task"),
            loaded_sections=[section],
            discovery_status="found",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        task_pos = result.index("My Task")
        code_pos = result.index("haive/client.py")
        assert task_pos < code_pos

    def test_dependency_outputs_follow_context(self):
        assembler = ContextAssembler()
        section = make_section("haive/client.py", "class Client: pass")
        result = assembler.assemble(
            task=make_task(),
            loaded_sections=[section],
            discovery_status="found",
            agent_config=make_agent_config(),
            dependency_outputs={"10": "output from task 10"},
        )
        code_pos = result.index("haive/client.py")
        dep_pos = result.index("output from task 10")
        assert code_pos < dep_pos

    def test_retry_feedback_appears_last(self):
        assembler = ContextAssembler()
        result = assembler.assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={"10": "dep output"},
            retry_feedback=["fix the type error"],
        )
        dep_pos = result.index("dep output")
        feedback_pos = result.index("fix the type error")
        assert dep_pos < feedback_pos


# ── task section ──────────────────────────────────────────────────────────────

class TestTaskSection:
    def test_title_and_description_present(self):
        result = ContextAssembler().assemble(
            task=make_task(title="Add retry", description="Use exponential backoff."),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "Add retry" in result
        assert "Use exponential backoff." in result

    def test_acceptance_criteria_included(self):
        result = ContextAssembler().assemble(
            task=make_task(acceptance_criteria=["must pass tests", "no regressions"]),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "must pass tests" in result
        assert "no regressions" in result

    def test_no_acceptance_criteria_section_when_empty(self):
        result = ContextAssembler().assemble(
            task=make_task(acceptance_criteria=[]),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "Acceptance criteria" not in result


# ── context section ───────────────────────────────────────────────────────────

class TestContextSection:
    def test_loaded_sections_appear_in_output(self):
        sections = [
            make_section("haive/client.py", "class Client: pass", "Core client."),
            make_section("haive/retry.py", "def retry(): ...", "Retry helper."),
        ]
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=sections,
            discovery_status="found",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "haive/client.py" in result
        assert "class Client: pass" in result
        assert "haive/retry.py" in result
        assert "def retry(): ..." in result

    def test_sections_appear_in_order(self):
        sections = [
            make_section("first.py", "x = 1"),
            make_section("second.py", "y = 2"),
        ]
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=sections,
            discovery_status="found",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert result.index("first.py") < result.index("second.py")

    def test_empty_sections_with_empty_expected_shows_scratch_note(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "creating new code from scratch" in result

    def test_empty_sections_with_empty_unexpected_shows_generic_note(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_unexpected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "Proceed based on the task description alone" in result

    def test_empty_sections_produces_no_blank_context_block(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "```" not in result


# ── dependency outputs ────────────────────────────────────────────────────────

class TestDependencyOutputs:
    def test_dependency_outputs_included(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={"5": "Task 5 produced an API client."},
        )
        assert "Task 5 produced an API client." in result

    def test_multiple_dependency_outputs_all_present(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={"3": "output three", "7": "output seven"},
        )
        assert "output three" in result
        assert "output seven" in result

    def test_no_dependency_section_when_empty(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
        )
        assert "Dependency Outputs" not in result


# ── retry feedback ────────────────────────────────────────────────────────────

class TestRetryFeedback:
    def test_feedback_present_on_retry(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
            retry_feedback=["fix the import error", "add type annotations"],
        )
        assert "fix the import error" in result
        assert "add type annotations" in result

    def test_no_feedback_section_on_first_attempt(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
            retry_feedback=None,
        )
        assert "Reviewer Feedback" not in result

    def test_empty_feedback_list_omits_section(self):
        result = ContextAssembler().assemble(
            task=make_task(),
            loaded_sections=[],
            discovery_status="empty_expected",
            agent_config=make_agent_config(),
            dependency_outputs={},
            retry_feedback=[],
        )
        assert "Reviewer Feedback" not in result
