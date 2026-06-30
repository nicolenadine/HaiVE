import os
from unittest.mock import MagicMock

import pytest

from haive.discovery.constants import AGENT_MD_MAX_GENERATION_RETRIES
from haive.discovery.file_index_service import AgentMdGenerationError, FileIndexService
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.tier import Tier

VALID_AGENT_MD = """\
## Files

task.py — Task and Project domain models with dependency tracking
state.py — ProjectState schema and schema-version guard
"""

INVALID_AGENT_MD = (
    "This is a prose paragraph that should be flagged as invalid content by the validator."
)


def make_turn(content: str) -> AgenticTurn:
    return AgenticTurn(tool_calls=[], content=content, model_used="test-model")


def make_tool_turn(name: str, **kwargs) -> AgenticTurn:
    return AgenticTurn(
        tool_calls=[ToolCall(id=f"tc_{name}", name=name, arguments=kwargs)],
        content=None,
        model_used="test-model",
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def tier():
    return Tier(models=["test-model"], max_attempts=1, context_budget=8000)


@pytest.fixture
def service(mock_client, tier):
    return FileIndexService(mock_client, tier)


# ── generate_all ──────────────────────────────────────────────────────────────

class TestGenerateAll:
    def test_generates_agent_md_for_source_directory(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        (tmp_path / "state.py").write_text("class State: pass")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        agent_md = tmp_path / "agent.md"
        assert agent_md.exists()
        assert "## Files" in agent_md.read_text()

    def test_no_agent_md_written_for_directory_with_no_source_files(
        self, service, mock_client, tmp_path
    ):
        empty = tmp_path / "empty"
        empty.mkdir()

        service.generate_all(str(tmp_path))

        assert not (tmp_path / "agent.md").exists()
        assert not (empty / "agent.md").exists()
        mock_client.call_single.assert_not_called()

    def test_retry_on_validation_failure_then_success(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.side_effect = [
            make_turn(INVALID_AGENT_MD),
            make_turn(VALID_AGENT_MD),
        ]

        service.generate_all(str(tmp_path))

        assert mock_client.call_single.call_count == 2
        assert (tmp_path / "agent.md").exists()

    def test_retry_message_includes_violations(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.side_effect = [
            make_turn(INVALID_AGENT_MD),
            make_turn(VALID_AGENT_MD),
        ]

        service.generate_all(str(tmp_path))

        retry_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        user_msg = next(m for m in retry_messages if m["role"] == "user")
        assert "violations" in user_msg["content"].lower()

    def test_exhausted_retries_raises_generation_error(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.return_value = make_turn(INVALID_AGENT_MD)

        with pytest.raises(AgentMdGenerationError, match="Failed to generate"):
            service.generate_all(str(tmp_path))

        assert mock_client.call_single.call_count == AGENT_MD_MAX_GENERATION_RETRIES

    def test_gitignore_excluded_directory_receives_no_agent_md(
        self, service, mock_client, tmp_path
    ):
        (tmp_path / ".gitignore").write_text(".venv\n__pycache__\n")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "site.py").write_text("# site-packages stub")
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        assert not (venv / "agent.md").exists()

    def test_gitignore_excluded_directory_is_not_listed_in_prompt(
        self, service, mock_client, tmp_path
    ):
        (tmp_path / ".gitignore").write_text("excluded_dir\n")
        excluded = tmp_path / "excluded_dir"
        excluded.mkdir()
        (excluded / "thing.py").write_text("x = 1")
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        first_call_messages = mock_client.call_single.call_args_list[0].kwargs["messages"]
        user_msg = next(m for m in first_call_messages if m["role"] == "user")
        assert "excluded_dir" not in user_msg["content"]

    def test_generates_agent_md_in_subdirectory(self, service, mock_client, tmp_path):
        subdir = tmp_path / "models"
        subdir.mkdir()
        (subdir / "task.py").write_text("class Task: pass")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        assert (subdir / "agent.md").exists()

    def test_agent_md_itself_is_not_listed_in_prompt(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        (tmp_path / "agent.md").write_text(VALID_AGENT_MD)
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        first_call_messages = mock_client.call_single.call_args_list[0].kwargs["messages"]
        user_msg = next(m for m in first_call_messages if m["role"] == "user")
        assert "  agent.md" not in user_msg["content"]

    def test_hidden_files_are_not_listed_in_prompt(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        (tmp_path / ".hidden.py").write_text("# hidden")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        first_call_messages = mock_client.call_single.call_args_list[0].kwargs["messages"]
        user_msg = next(m for m in first_call_messages if m["role"] == "user")
        assert ".hidden.py" not in user_msg["content"]

    def test_non_source_files_do_not_trigger_generation(self, service, mock_client, tmp_path):
        (tmp_path / "output.log").write_text("log entry")

        service.generate_all(str(tmp_path))

        assert not (tmp_path / "agent.md").exists()
        mock_client.call_single.assert_not_called()

    def test_written_content_passes_validator(self, service, mock_client, tmp_path):
        (tmp_path / "task.py").write_text("class Task: pass")
        mock_client.call_single.return_value = make_turn(VALID_AGENT_MD)

        service.generate_all(str(tmp_path))

        from haive.discovery.agent_md import AgentMdValidator
        content = (tmp_path / "agent.md").read_text()
        assert AgentMdValidator().validate(content) == []


# ── validate_all ──────────────────────────────────────────────────────────────

class TestValidateAll:
    def test_returns_empty_dict_when_all_files_valid(self, service, tmp_path):
        (tmp_path / "agent.md").write_text(VALID_AGENT_MD)

        result = service.validate_all(str(tmp_path))

        assert result == {}

    def test_reports_violations_for_invalid_file(self, service, tmp_path):
        (tmp_path / "agent.md").write_text("no files section here")

        result = service.validate_all(str(tmp_path))

        assert "agent.md" in result
        assert any("Missing required section" in v for v in result["agent.md"])

    def test_never_calls_llm(self, service, mock_client, tmp_path):
        (tmp_path / "agent.md").write_text(VALID_AGENT_MD)

        service.validate_all(str(tmp_path))

        mock_client.call_single.assert_not_called()

    def test_finds_violations_in_subdirectory(self, service, tmp_path):
        subdir = tmp_path / "models"
        subdir.mkdir()
        (subdir / "agent.md").write_text("no files section")

        result = service.validate_all(str(tmp_path))

        assert any("models" in k for k in result)

    def test_only_reports_files_with_violations(self, service, tmp_path):
        (tmp_path / "agent.md").write_text(VALID_AGENT_MD)
        subdir = tmp_path / "models"
        subdir.mkdir()
        (subdir / "agent.md").write_text("bad content missing files section")

        result = service.validate_all(str(tmp_path))

        assert "agent.md" not in result
        assert any("models" in k for k in result)


# ── gitignore helpers ─────────────────────────────────────────────────────────

class TestGitignoreHandling:
    def test_no_gitignore_returns_empty_patterns(self, service, tmp_path):
        patterns = service._load_gitignore_patterns(str(tmp_path))
        assert patterns == []

    def test_gitignore_comments_and_blank_lines_ignored(self, service, tmp_path):
        (tmp_path / ".gitignore").write_text("# comment\n\n.venv\n")
        patterns = service._load_gitignore_patterns(str(tmp_path))
        assert patterns == [".venv"]

    def test_trailing_slash_stripped_from_patterns(self, service, tmp_path):
        (tmp_path / ".gitignore").write_text("dist/\nnode_modules/\n")
        patterns = service._load_gitignore_patterns(str(tmp_path))
        assert "dist" in patterns
        assert "node_modules" in patterns

    def test_git_directory_always_skipped(self, service):
        assert service._should_skip(".git", []) is True

    def test_pattern_match_skips_directory(self, service):
        assert service._should_skip(".venv", [".venv"]) is True
        assert service._should_skip("node_modules", ["node_modules"]) is True

    def test_non_matching_directory_not_skipped(self, service):
        assert service._should_skip("haive", [".venv"]) is False


# ── load_sections ─────────────────────────────────────────────────────────────

from haive.models.discovery import DiscoveredSection, DiscoveryResult


def _section(file: str, *, full: bool = True, start: int | None = None, end: int | None = None, reason: str = "relevant") -> DiscoveredSection:
    return DiscoveredSection(file=file, symbol=None, start_line=start, end_line=end, full=full, reason=reason)


def _result(*sections: DiscoveredSection) -> DiscoveryResult:
    return DiscoveryResult(sections=list(sections), status="found")


class TestLoadSections:
    def test_full_section_returns_entire_file(self, service, tmp_path):
        (tmp_path / "task.py").write_text("line1\nline2\nline3\n")
        result = _result(_section("task.py", full=True))
        loaded = service.load_sections(result, str(tmp_path), token_budget=10000)
        assert len(loaded) == 1
        assert loaded[0].source == "line1\nline2\nline3\n"
        assert loaded[0].file == "task.py"
        assert loaded[0].reason == "relevant"

    def test_line_range_returns_exact_slice(self, service, tmp_path):
        (tmp_path / "task.py").write_text("a\nb\nc\nd\ne\n")
        result = _result(_section("task.py", full=False, start=2, end=4))
        loaded = service.load_sections(result, str(tmp_path), token_budget=10000)
        assert loaded[0].source == "b\nc\nd\n"

    def test_missing_file_raises_file_not_found(self, service, tmp_path):
        result = _result(_section("ghost.py", full=True))
        with pytest.raises(FileNotFoundError, match="ghost.py"):
            service.load_sections(result, str(tmp_path), token_budget=10000)

    def test_sections_dropped_when_budget_exceeded(self, service, tmp_path):
        # Each file is ~100 chars → ~25 tokens. Budget of 30 fits only the first.
        content = "x" * 100
        (tmp_path / "a.py").write_text(content)
        (tmp_path / "b.py").write_text(content)
        result = _result(
            _section("a.py", full=True, reason="first"),
            _section("b.py", full=True, reason="second"),
        )
        loaded = service.load_sections(result, str(tmp_path), token_budget=30)
        assert len(loaded) == 1
        assert loaded[0].reason == "first"

    def test_priority_order_preserved(self, service, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.py").write_text("c")
        result = _result(
            _section("a.py", full=True, reason="most relevant"),
            _section("b.py", full=True, reason="second"),
            _section("c.py", full=True, reason="third"),
        )
        loaded = service.load_sections(result, str(tmp_path), token_budget=10000)
        assert [s.reason for s in loaded] == ["most relevant", "second", "third"]

    def test_empty_discovery_result_returns_empty_list(self, service, tmp_path):
        result = DiscoveryResult(sections=[], status="empty")
        loaded = service.load_sections(result, str(tmp_path), token_budget=10000)
        assert loaded == []
