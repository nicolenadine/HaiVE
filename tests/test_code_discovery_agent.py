from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
from haive.discovery.constants import CODE_DISCOVERY_MAX_TOOL_CALLS
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.models.discovery import DiscoveryResult
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TIER = Tier(models=["test-model"], max_attempts=1, context_budget=8000)
_ESCALATION_TIER = Tier(models=["escalation-model"], max_attempts=1, context_budget=8000)


def _make_task(
    title: str = "Add task validation",
    description: str = "Validate task input.",
    agent_role: AgentRole = AgentRole.IMPLEMENTATION_AGENT,
) -> Task:
    return Task(
        task_id="1",
        title=title,
        description=description,
        agent_role=agent_role,
        complexity=Complexity.MEDIUM,
        depends_on=[],
        acceptance_criteria=["ac"],
        status=TaskStatus.PENDING,
    )


def _tool_call(name: str, **kwargs) -> ToolCall:
    return ToolCall(id=f"tc_{name}", name=name, arguments=kwargs)


def _turn_with_tools(*tool_calls: ToolCall) -> AgenticTurn:
    return AgenticTurn(tool_calls=list(tool_calls), content=None, model_used="test-model")


def _turn_with_content(content: str) -> AgenticTurn:
    return AgenticTurn(tool_calls=[], content=content, model_used="test-model")


def _found_json(file: str, symbol: str | None = None, full: bool = True) -> str:
    section = {
        "file": file,
        "symbol": symbol,
        "start_line": None,
        "end_line": None,
        "full": full,
        "reason": "Relevant to the task.",
    }
    return json.dumps({"sections": [section], "status": "found"})


_EMPTY_JSON = json.dumps({"sections": [], "status": "empty"})

_ROOT_AGENT_MD = """\
## Files

models/ — Pydantic data models for tasks, state, and verdicts
cli/ — Typer CLI entry point and command implementations
"""

_MODELS_AGENT_MD = """\
## Files

task.py — Task and Project domain models with dependency tracking
  Task (class) — 15-25
state.py — ProjectState schema and schema-version guard
"""

_CLI_AGENT_MD = """\
## Files

cli.py — Typer CLI entry point for the haive harness
"""


@pytest.fixture
def repo_root():
    """Temp directory tree with agent.md files at root, models/, and cli/.

    Also creates the real source files those agent.md files describe (just
    "task.py", the one tests actually reference) -- CodeDiscoveryAgent now
    verifies a discovered file exists before trusting it, so a test asserting
    a section survives must back it with a real file, the same way a
    genuinely accurate agent.md would.
    """
    with tempfile.TemporaryDirectory() as root:
        Path(root, "agent.md").write_text(_ROOT_AGENT_MD)
        Path(root, "models").mkdir()
        Path(root, "models", "agent.md").write_text(_MODELS_AGENT_MD)
        Path(root, "models", "task.py").write_text("class Task:\n    pass\n")
        Path(root, "cli").mkdir()
        Path(root, "cli", "agent.md").write_text(_CLI_AGENT_MD)
        yield root


@pytest.fixture
def mock_client():
    return MagicMock(spec=ModelClient)


@pytest.fixture
def agent(mock_client):
    return CodeDiscoveryAgent(mock_client, _TIER)


@pytest.fixture
def escalating_agent(mock_client):
    return CodeDiscoveryAgent(mock_client, _TIER, escalation_tier=_ESCALATION_TIER)


# ---------------------------------------------------------------------------
# Happy-path: targeted discovery
# ---------------------------------------------------------------------------

class TestTargetedDiscovery:
    def test_finds_relevant_file_in_subdirectory(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_tools(_tool_call("read_agent_md", directory="models")),
            _turn_with_content(_found_json("models/task.py")),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "found"
        assert len(result.sections) == 1
        assert result.sections[0].file == "models/task.py"

    def test_does_not_read_unrelated_sibling_directory(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_tools(_tool_call("read_agent_md", directory="models")),
            _turn_with_content(_found_json("models/task.py")),
        ]

        agent.discover(_make_task(), repo_root, token_budget=4000)

        # Only 3 call_single calls: root, models/, final answer — cli/ never read
        assert mock_client.call_single.call_count == 3

    def test_list_subdirectories_tool_works(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("list_subdirectories", directory=".")),
            _turn_with_content(_found_json("models/task.py")),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "found"

    def test_symbol_level_section_is_accepted_for_scaffold_tasks(self, agent, mock_client, repo_root):
        # Scaffold tasks create brand-new files, so there's no existing content
        # to lose — they're exempt from the full-file override below.
        section = {
            "file": "models/task.py",
            "symbol": "Task",
            "start_line": 15,
            "end_line": 25,
            "full": False,
            "reason": "Task class defines the domain model.",
        }
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_content(json.dumps({"sections": [section], "status": "found"})),
        ]

        result = agent.discover(
            _make_task(agent_role=AgentRole.SCAFFOLD_AGENT), repo_root, token_budget=4000
        )

        assert result.sections[0].symbol == "Task"
        assert result.sections[0].start_line == 15
        assert result.sections[0].end_line == 25
        assert result.sections[0].full is False

    def test_non_scaffold_tasks_always_get_full_file_sections(self, agent, mock_client, repo_root):
        # A code-editing submission always replaces a file's entire content,
        # so a partial symbol range can never safely become that replacement —
        # non-scaffold tasks are forced to full=True regardless of what the
        # discovery agent itself proposed.
        section = {
            "file": "models/task.py",
            "symbol": "Task",
            "start_line": 15,
            "end_line": 25,
            "full": False,
            "reason": "Task class defines the domain model.",
        }
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_content(json.dumps({"sections": [section], "status": "found"})),
        ]

        result = agent.discover(
            _make_task(agent_role=AgentRole.IMPLEMENTATION_AGENT), repo_root, token_budget=4000
        )

        assert result.sections[0].full is True
        assert result.sections[0].start_line is None
        assert result.sections[0].end_line is None
        assert result.sections[0].symbol is None

    def test_non_scaffold_tasks_deduplicate_multiple_sections_of_same_file(
        self, agent, mock_client, repo_root
    ):
        sections = [
            {
                "file": "models/task.py", "symbol": "Task", "start_line": 15,
                "end_line": 25, "full": False, "reason": "First relevant symbol.",
            },
            {
                "file": "models/task.py", "symbol": "TaskComment", "start_line": 30,
                "end_line": 40, "full": False, "reason": "Second relevant symbol, same file.",
            },
        ]
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_content(json.dumps({"sections": sections, "status": "found"})),
        ]

        result = agent.discover(
            _make_task(agent_role=AgentRole.IMPLEMENTATION_AGENT), repo_root, token_budget=4000
        )

        assert len(result.sections) == 1
        assert result.sections[0].file == "models/task.py"
        assert result.sections[0].full is True


# ---------------------------------------------------------------------------
# Guardrail: max tool calls
# ---------------------------------------------------------------------------

class TestGuardrailCutoff:
    def test_cutoff_returns_result_not_exception(self, agent, mock_client, repo_root):
        # Fill up all tool call slots with read_agent_md calls, then final answer
        tool_turns = [
            _turn_with_tools(_tool_call("read_agent_md", directory="."))
            for _ in range(CODE_DISCOVERY_MAX_TOOL_CALLS)
        ]
        mock_client.call_single.side_effect = tool_turns + [
            _turn_with_content(_found_json("models/task.py"))
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert isinstance(result, DiscoveryResult)

    def test_cutoff_injects_force_answer_message(self, agent, mock_client, repo_root):
        tool_turns = [
            _turn_with_tools(_tool_call("read_agent_md", directory="."))
            for _ in range(CODE_DISCOVERY_MAX_TOOL_CALLS)
        ]
        mock_client.call_single.side_effect = tool_turns + [
            _turn_with_content(_EMPTY_JSON)
        ]

        agent.discover(_make_task(), repo_root, token_budget=4000)

        # The final call_single must NOT include tools (force-answer call)
        final_call_kwargs = mock_client.call_single.call_args
        assert final_call_kwargs.kwargs.get("tools") is None or "tools" not in final_call_kwargs.kwargs


# ---------------------------------------------------------------------------
# Empty result
# ---------------------------------------------------------------------------

class TestEmptyResult:
    def test_empty_status_when_llm_finds_nothing(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_content(_EMPTY_JSON),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "empty"
        assert result.sections == []

    def test_missing_root_agent_md_tool_returns_error_string(self, agent, mock_client, tmp_path):
        # tmp_path has no agent.md — tool should return error string, not raise
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=".")),
            _turn_with_content(_EMPTY_JSON),
        ]

        result = agent.discover(_make_task(), str(tmp_path), token_budget=4000)

        assert result.status == "empty"
        # Verify the tool result message contained the error string
        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
        assert "No agent.md found" in tool_msg["content"]


# ---------------------------------------------------------------------------
# Parse failure handling
# ---------------------------------------------------------------------------

class TestParseFailure:
    def test_malformed_json_returns_empty_not_exception(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_content("I found some relevant files in the models directory."),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "empty"
        assert result.sections == []

    def test_json_wrapped_in_markdown_fences_is_parsed(self, agent, mock_client, repo_root):
        wrapped = f"```json\n{_found_json('models/task.py')}\n```"
        mock_client.call_single.side_effect = [_turn_with_content(wrapped)]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "found"

    def test_empty_content_returns_empty(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [_turn_with_content("")]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.status == "empty"


# ---------------------------------------------------------------------------
# Tool execution edge cases
# ---------------------------------------------------------------------------

class TestToolExecution:
    def test_unknown_tool_name_returns_error_string(self, agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("nonexistent_tool", directory=".")),
            _turn_with_content(_EMPTY_JSON),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert isinstance(result, DiscoveryResult)
        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
        assert "Unknown tool" in tool_msg["content"]

    def test_list_subdirectories_on_missing_dir_returns_error_string(
        self, agent, mock_client, repo_root
    ):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("list_subdirectories", directory="nonexistent")),
            _turn_with_content(_EMPTY_JSON),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
        assert "Directory not found" in tool_msg["content"]

    @pytest.mark.parametrize("traversal_path", [
        "../../../etc",
        "../../..",
        "/etc",
        "/",
    ])
    def test_path_traversal_is_rejected(self, agent, mock_client, repo_root, traversal_path):
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_agent_md", directory=traversal_path)),
            _turn_with_content(_EMPTY_JSON),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        tool_msg = next(m for m in second_call_messages if m["role"] == "tool")
        assert "Access denied" in tool_msg["content"]
        assert result.status == "empty"


# ---------------------------------------------------------------------------
# Escalation: a demonstrated problem earns a stronger model, not every call
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_healthy_result_never_escalates(self, escalating_agent, mock_client, repo_root):
        mock_client.call_single.side_effect = [
            _turn_with_content(_found_json("models/task.py")),
        ]

        result = escalating_agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.sections[0].file == "models/task.py"
        assert mock_client.call_single.call_count == 1

    def test_escalates_when_returned_file_does_not_exist(
        self, escalating_agent, mock_client, repo_root
    ):
        mock_client.call_single.side_effect = [
            _turn_with_content(_found_json("models/nonexistent.py")),
            _turn_with_content(_found_json("models/task.py")),
        ]

        result = escalating_agent.discover(_make_task(), repo_root, token_budget=4000)

        assert len(result.sections) == 1
        assert result.sections[0].file == "models/task.py"
        assert mock_client.call_single.call_count == 2
        escalated_call = mock_client.call_single.call_args_list[1]
        assert escalated_call.kwargs["tier"] is _ESCALATION_TIER

    def test_escalates_on_empty_unexpected_then_finds_result(
        self, escalating_agent, mock_client, repo_root
    ):
        mock_client.call_single.side_effect = [
            _turn_with_content(_EMPTY_JSON),
            _turn_with_content(_found_json("models/task.py")),
        ]

        result = escalating_agent.discover(
            _make_task(agent_role=AgentRole.IMPLEMENTATION_AGENT), repo_root, token_budget=4000
        )

        assert result.status == "found"
        assert result.sections[0].file == "models/task.py"
        assert mock_client.call_single.call_count == 2

    def test_no_escalation_for_scaffold_role_even_if_empty(
        self, escalating_agent, mock_client, repo_root
    ):
        mock_client.call_single.side_effect = [_turn_with_content(_EMPTY_JSON)]

        result = escalating_agent.discover(
            _make_task(agent_role=AgentRole.SCAFFOLD_AGENT), repo_root, token_budget=4000
        )

        assert result.status == "empty"
        assert mock_client.call_single.call_count == 1

    def test_still_missing_after_escalation_is_dropped_not_raised(
        self, escalating_agent, mock_client, repo_root
    ):
        mock_client.call_single.side_effect = [
            _turn_with_content(_found_json("models/nonexistent.py")),
            _turn_with_content(_found_json("models/still_nonexistent.py")),
        ]

        result = escalating_agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.sections == []
        assert result.status == "empty"
        assert mock_client.call_single.call_count == 2

    def test_non_escalating_agent_drops_missing_file_without_retry(
        self, agent, mock_client, repo_root
    ):
        # `agent` (no escalation_tier configured) must never attempt a second
        # call, even when the first result names a nonexistent file.
        mock_client.call_single.side_effect = [
            _turn_with_content(_found_json("models/nonexistent.py")),
        ]

        result = agent.discover(_make_task(), repo_root, token_budget=4000)

        assert result.sections == []
        assert result.status == "empty"
        assert mock_client.call_single.call_count == 1
