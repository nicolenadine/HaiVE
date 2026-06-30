from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from haive.discovery.code_discovery_prompt import CODE_DISCOVERY_SYSTEM_PROMPT
from haive.discovery.constants import CODE_DISCOVERY_MAX_TOKENS, CODE_DISCOVERY_MAX_TOOL_CALLS
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.models.discovery import DiscoveredSection, DiscoveryResult
from haive.models.task import Task

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_agent_md",
            "description": (
                "Read the agent.md index file for a repo-relative directory. "
                "Pass '.' for the repo root. Returns the file content, or an "
                "error message if no agent.md exists in that directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": (
                            "Relative path inside the project repo, e.g. '.' or "
                            "'haive/models'. Must not contain '..' or start with '/'. "
                            "Paths outside the repo are rejected."
                        ),
                    }
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_subdirectories",
            "description": (
                "List the immediate subdirectory names inside a repo-relative "
                "directory. Returns a newline-separated list of names, or "
                "'No subdirectories.' if there are none."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": (
                            "Relative path inside the project repo, e.g. '.' or "
                            "'haive'. Must not contain '..' or start with '/'."
                        ),
                    }
                },
                "required": ["directory"],
            },
        },
    },
]


def _build_system_prompt() -> str:
    return CODE_DISCOVERY_SYSTEM_PROMPT


def _build_user_prompt(task: Task) -> str:
    return f"Task: {task.title}\n\n{task.description}"


class CodeDiscoveryAgent:
    """Navigates the agent.md tree to find files and symbols relevant to a task.

    Uses LLM tool calling with two tools (read_agent_md, list_subdirectories)
    to explore the repo top-down. Bounded by CODE_DISCOVERY_MAX_TOOL_CALLS.
    Returns DiscoveryResult(sections=[], status="empty") rather than raising
    when nothing is found or the LLM output cannot be parsed.
    """

    def __init__(self, model_client: ModelClient, tier: Tier) -> None:
        self._client = model_client
        self._tier = tier

    def discover(self, task: Task, root: str, token_budget: int) -> DiscoveryResult:
        messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": _build_user_prompt(task)},
        ]
        tool_call_count = 0

        while tool_call_count < CODE_DISCOVERY_MAX_TOOL_CALLS:
            turn = self._client.call_single(
                tier=self._tier,
                messages=messages,
                max_tokens=CODE_DISCOVERY_MAX_TOKENS,
                tools=_TOOLS,
            )
            messages.append(self._assistant_message(turn))

            if not turn.tool_calls:
                return self._parse_result(turn.content or "")

            for tc in turn.tool_calls:
                result = self._execute_tool(tc.name, tc.arguments, root)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                tool_call_count += 1

        # Guardrail: force a final answer without offering more tools.
        messages.append({
            "role": "user",
            "content": "Tool call limit reached. Return your best result now as JSON.",
        })
        final = self._client.call_single(
            tier=self._tier,
            messages=messages,
            max_tokens=CODE_DISCOVERY_MAX_TOKENS,
        )
        return self._parse_result(final.content or "")

    # ── internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _assistant_message(turn: AgenticTurn) -> dict:
        msg: dict = {"role": "assistant", "content": turn.content}
        if turn.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in turn.tool_calls
            ]
        return msg

    def _execute_tool(self, name: str, arguments: dict, root: str) -> str:
        if name == "read_agent_md":
            return self._read_agent_md(arguments.get("directory", "."), root)
        if name == "list_subdirectories":
            return self._list_subdirectories(arguments.get("directory", "."), root)
        return f"Unknown tool: {name}"

    @staticmethod
    def _resolve_within_root(directory: str, root: str) -> Path | None:
        """Return the resolved path only if it stays inside root; None otherwise."""
        root_resolved = Path(root).resolve()
        candidate = (root_resolved / directory).resolve()
        try:
            candidate.relative_to(root_resolved)
            return candidate
        except ValueError:
            return None

    def _read_agent_md(self, directory: str, root: str) -> str:
        safe = self._resolve_within_root(directory, root)
        if safe is None:
            return f"Access denied: {directory!r} is outside the project repo"
        path = safe / "agent.md"
        if not path.is_file():
            return f"No agent.md found in {directory}"
        return path.read_text(encoding="utf-8")

    def _list_subdirectories(self, directory: str, root: str) -> str:
        safe = self._resolve_within_root(directory, root)
        if safe is None:
            return f"Access denied: {directory!r} is outside the project repo"
        if not safe.is_dir():
            return f"Directory not found: {directory}"
        subdirs = sorted(
            d.name for d in safe.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        return "\n".join(subdirs) if subdirs else "No subdirectories."

    @staticmethod
    def _parse_result(content: str) -> DiscoveryResult:
        text = content.strip()

        # Try direct parse first (ideal: response is just the JSON object).
        try:
            return DiscoveryResult.model_validate_json(text)
        except (ValidationError, ValueError):
            pass

        # Extract from markdown code fences if the model wrapped the JSON.
        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            try:
                return DiscoveryResult.model_validate_json(fence_match.group(1).strip())
            except (ValidationError, ValueError):
                pass

        # Last resort: find the outermost { ... } in the text.
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i, ch in enumerate(text[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return DiscoveryResult.model_validate_json(text[brace_start : i + 1])
                        except (ValidationError, ValueError):
                            break

        return DiscoveryResult(sections=[], status="empty")
