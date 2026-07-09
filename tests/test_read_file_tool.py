from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from haive.execution.read_file_tool import read_file_for_tool_call, run_tool_loop
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier

_TIER = Tier(models=["test-model"], max_attempts=1, context_budget=8000)


def _tool_call(name: str, **kwargs) -> ToolCall:
    return ToolCall(id=f"tc_{name}", name=name, arguments=kwargs)


def _turn_with_tools(*tool_calls: ToolCall) -> AgenticTurn:
    return AgenticTurn(tool_calls=list(tool_calls), content=None, model_used="test-model")


def _turn_with_content(content: str) -> AgenticTurn:
    return AgenticTurn(tool_calls=[], content=content, model_used="test-model")


@pytest.fixture
def mock_client():
    return MagicMock(spec=ModelClient)


@pytest.fixture
def base_messages():
    return [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Do the task."},
    ]


# ── read_file_for_tool_call ────────────────────────────────────────────────

class TestReadFileForToolCall:
    def test_reads_existing_file(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1\n")
        content, tokens = read_file_for_tool_call("foo.py", str(tmp_path), remaining_budget=1000)
        assert content == "x = 1\n"
        assert tokens > 0

    def test_missing_file_returns_error_text(self, tmp_path):
        content, tokens = read_file_for_tool_call("ghost.py", str(tmp_path), remaining_budget=1000)
        assert "not found" in content.lower()
        assert tokens == 0

    def test_path_traversal_denied(self, tmp_path):
        content, tokens = read_file_for_tool_call("../../etc/passwd", str(tmp_path), remaining_budget=1000)
        assert "access denied" in content.lower()
        assert tokens == 0

    def test_truncates_when_over_budget(self, tmp_path):
        (tmp_path / "big.py").write_text("x" * 10_000)
        content, tokens = read_file_for_tool_call("big.py", str(tmp_path), remaining_budget=10)
        assert "truncated" in content.lower()
        assert tokens == 10


# ── run_tool_loop ─────────────────────────────────────────────────────────

class TestRunToolLoop:
    def test_immediate_final_answer_no_tools_called(self, mock_client, base_messages):
        mock_client.call_single.return_value = _turn_with_content('{"passed": true}')

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root="/tmp", budget=1000, max_rounds=5,
        )

        assert result.content == '{"passed": true}'
        assert mock_client.call_single.call_count == 1

    def test_single_round_trip_reads_file_and_returns_final(self, mock_client, base_messages, tmp_path):
        (tmp_path / "extra.py").write_text("class Extra: pass")
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check the caller")),
            _turn_with_content('{"passed": false}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=1000, max_rounds=5,
        )

        assert result.content == '{"passed": false}'
        assert mock_client.call_single.call_count == 2
        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        assert any("class Extra: pass" in (m.get("content") or "") for m in second_call_messages)

    def test_multiple_round_trips(self, mock_client, base_messages, tmp_path):
        (tmp_path / "a.py").write_text("a = 1")
        (tmp_path / "b.py").write_text("b = 2")
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="a.py", reason="r1")),
            _turn_with_tools(_tool_call("read_file", path="b.py", reason="r2")),
            _turn_with_content('{"passed": true}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=1000, max_rounds=5,
        )

        assert result.content == '{"passed": true}'
        assert mock_client.call_single.call_count == 3

    def test_does_not_mutate_caller_messages_list(self, mock_client, base_messages, tmp_path):
        original_len = len(base_messages)
        (tmp_path / "extra.py").write_text("x = 1")
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check")),
            _turn_with_content('{"passed": true}'),
        ]

        run_tool_loop(mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=1000, max_rounds=5)

        assert len(base_messages) == original_len

    def test_budget_exhaustion_forces_final_answer(self, mock_client, base_messages, tmp_path):
        (tmp_path / "big.py").write_text("x" * 10_000)
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="big.py", reason="check")),
            _turn_with_content('{"passed": false}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=10, max_rounds=5,
        )

        assert result.content == '{"passed": false}'
        final_call_kwargs = mock_client.call_single.call_args_list[-1].kwargs
        assert not final_call_kwargs.get("tools")

    def test_round_limit_forces_final_answer_without_tools(self, mock_client, base_messages, tmp_path):
        (tmp_path / "extra.py").write_text("x = 1")
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check")),
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check again")),
            _turn_with_content('{"passed": true}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=10_000, max_rounds=2,
        )

        assert result.content == '{"passed": true}'
        assert mock_client.call_single.call_count == 3
        final_call_kwargs = mock_client.call_single.call_args_list[-1].kwargs
        assert not final_call_kwargs.get("tools")

    def test_remaining_budget_decreases_after_read(self, mock_client, base_messages, tmp_path):
        (tmp_path / "extra.py").write_text("x" * 40)
        mock_client.call_single.side_effect = [
            _turn_with_tools(_tool_call("read_file", path="extra.py", reason="check")),
            _turn_with_content('{"passed": true}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root=str(tmp_path), budget=1000, max_rounds=5,
        )

        assert result.remaining_budget < 1000

    def test_prose_with_no_json_is_not_accepted_as_final_answer(self, mock_client, base_messages):
        # Regression test: a model reasoning out loud without calling a tool
        # ("here's my plan...") must not be handed straight to the validator
        # as if it were the final answer — it's guaranteed to fail schema
        # validation there, burning a whole separate attempt (fresh
        # discovery, fresh conversation) for something recoverable within
        # this same conversation.
        mock_client.call_single.side_effect = [
            _turn_with_content("Based on the code I've read, here's my plan: I'll use pathlib."),
            _turn_with_content('{"passed": true}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root="/tmp", budget=1000, max_rounds=5,
        )

        assert result.content == '{"passed": true}'
        assert mock_client.call_single.call_count == 2
        second_call_messages = mock_client.call_single.call_args_list[1].kwargs["messages"]
        assert "wasn't your final answer" in second_call_messages[-1]["content"]

    def test_content_containing_a_brace_is_accepted_immediately(self, mock_client, base_messages):
        # A response with any '{' is treated as a genuine answer attempt —
        # real validation (and any retry it triggers) is OutputValidator's
        # job, not run_tool_loop's.
        mock_client.call_single.return_value = _turn_with_content("not quite json {")

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root="/tmp", budget=1000, max_rounds=5,
        )

        assert result.content == "not quite json {"
        assert mock_client.call_single.call_count == 1

    def test_repeated_prose_eventually_hits_round_limit(self, mock_client, base_messages):
        # The nudge must still respect max_rounds — a model that never
        # produces anything brace-like must not loop forever.
        mock_client.call_single.side_effect = [
            _turn_with_content("Thinking about approach one..."),
            _turn_with_content("Thinking about approach two..."),
            _turn_with_content('{"passed": true}'),
        ]

        result = run_tool_loop(
            mock_client, _TIER, base_messages, max_tokens=1024, root="/tmp", budget=1000, max_rounds=2,
        )

        assert result.content == '{"passed": true}'
        assert mock_client.call_single.call_count == 3
        final_call_kwargs = mock_client.call_single.call_args_list[-1].kwargs
        assert not final_call_kwargs.get("tools")
