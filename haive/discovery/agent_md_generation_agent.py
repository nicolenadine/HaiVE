from __future__ import annotations

import json
import os
from pathlib import Path

from haive.discovery.agent_md_generation_prompt import AGENT_MD_GENERATION_SYSTEM_PROMPT
from haive.discovery.constants import AGENT_MD_GENERATION_MAX_TOKENS
from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full content of a source file inside the project repo. "
                "Pass a repo-relative path, e.g. 'haive/models/task.py'. "
                "Paths must be relative (no '..' components, no leading '/'). "
                "Returns the file content as a string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Repo-relative path to the file, e.g. 'haive/models/task.py'. "
                            "Must not contain '..' or start with '/'."
                        ),
                    }
                },
                "required": ["path"],
            },
        },
    }
]


def _build_user_prompt(
    dir_path: str,
    source_files: list[str],
    subdirs: list[str],
    root: str,
    prior_violations: list[str] | None = None,
) -> str:
    rel = os.path.relpath(dir_path, root) if dir_path != root else "."
    parts = [
        f"Generate an agent.md for the directory: {rel}",
        "",
        "Source files (read each one before writing the agent.md):",
    ]
    for f in source_files:
        file_path = f if rel == "." else f"{rel}/{f}"
        parts.append(f"  {file_path}")
    if subdirs:
        parts.append("")
        parts.append(
            "Immediate subdirectories (read each one's agent.md for its description):"
        )
        for d in subdirs:
            agent_md_path = f"{d}/agent.md" if rel == "." else f"{rel}/{d}/agent.md"
            parts.append(f"  {d}/  →  read_file('{agent_md_path}')")
    parts.append("")
    parts.append(
        "Read every source file above using read_file. "
        "For subdirectories, read their agent.md to write an accurate one-line description "
        "of what that subdirectory contains. "
        "If a subdirectory has no agent.md, write a brief description based on its name. "
        "Do not list agent.md as a file entry — it is never included in the output. "
        "Start your response directly with '## Files' — no preamble."
    )
    if prior_violations:
        violation_lines = "\n".join(f"  - {v}" for v in prior_violations)
        parts.append("")
        parts.append(
            f"Your previous attempt had format violations — fix them all:\n{violation_lines}"
        )
    return "\n".join(parts)


def _build_update_user_prompt(
    dir_path: str,
    changed_files: list[str],
    existing_content: str,
    root: str,
    prior_violations: list[str] | None = None,
) -> str:
    rel = os.path.relpath(dir_path, root) if dir_path != root else "."
    parts = [
        f"Update the agent.md for directory: {rel}",
        "",
        "Current agent.md (preserve all unchanged entries verbatim):",
        "",
        existing_content.strip(),
        "",
        "Files that were added or modified (read each one, then rewrite only their entries):",
    ]
    for f in changed_files:
        file_path = f if rel == "." else f"{rel}/{f}"
        parts.append(f"  {file_path}")
    parts.append("")
    parts.append(
        "Instructions: read each changed file using read_file. "
        "Return the complete updated agent.md. "
        "Preserve every unchanged file entry and its symbol sub-entries verbatim. "
        "Only rewrite entries for the files listed above. "
        "If a listed file is new (not present in the existing agent.md), insert its entry "
        "in alphabetical order among the other file entries. "
        "Do not list agent.md as a file entry. "
        "Start your response directly with '## Files' — no preamble."
    )
    if prior_violations:
        violation_lines = "\n".join(f"  - {v}" for v in prior_violations)
        parts.append("")
        parts.append(
            f"Your previous attempt had format violations — fix them all:\n{violation_lines}"
        )
    return "\n".join(parts)


class AgentMdGenerationAgent:
    """Reads each source file in a directory via tool calling and writes an agent.md.

    Uses a single read_file tool. The agent reads files on demand then produces
    the agent.md content as its final (non-tool) response. Bounded by
    len(source_files) + 5 tool calls to prevent runaway loops.
    """

    def __init__(self, model_client: ModelClient, tier: Tier) -> None:
        self._client = model_client
        self._tier = tier

    def generate(
        self,
        dir_path: str,
        source_files: list[str],
        subdirs: list[str],
        root: str,
        prior_violations: list[str] | None = None,
    ) -> str:
        messages: list[dict] = [
            {"role": "system", "content": AGENT_MD_GENERATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    dir_path, source_files, subdirs, root, prior_violations
                ),
            },
        ]
        max_tool_calls = len(source_files) + len(subdirs) + 5
        tool_call_count = 0

        while tool_call_count < max_tool_calls:
            turn = self._client.call_single(
                tier=self._tier,
                messages=messages,
                max_tokens=AGENT_MD_GENERATION_MAX_TOKENS,
                tools=_TOOLS,
            )
            messages.append(self._assistant_message(turn))

            if not turn.tool_calls:
                return (turn.content or "").strip()

            for tc in turn.tool_calls:
                result = self._read_file(tc.arguments.get("path", ""), root)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                tool_call_count += 1

        # Guardrail: force final response without offering more tools
        messages.append({
            "role": "user",
            "content": "Write the agent.md now based on what you have read. Start with '## Files'.",
        })
        final = self._client.call_single(
            tier=self._tier,
            messages=messages,
            max_tokens=AGENT_MD_GENERATION_MAX_TOKENS,
        )
        return (final.content or "").strip()

    def update(
        self,
        dir_path: str,
        changed_files: list[str],
        existing_content: str,
        root: str,
        prior_violations: list[str] | None = None,
    ) -> str:
        """Incrementally update an existing agent.md for added/modified files only.

        Reads each changed file via read_file, then returns the full updated
        agent.md with unchanged entries preserved verbatim.
        """
        messages: list[dict] = [
            {"role": "system", "content": AGENT_MD_GENERATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_update_user_prompt(
                    dir_path, changed_files, existing_content, root, prior_violations
                ),
            },
        ]
        max_tool_calls = len(changed_files) + 5
        tool_call_count = 0

        while tool_call_count < max_tool_calls:
            turn = self._client.call_single(
                tier=self._tier,
                messages=messages,
                max_tokens=AGENT_MD_GENERATION_MAX_TOKENS,
                tools=_TOOLS,
            )
            messages.append(self._assistant_message(turn))

            if not turn.tool_calls:
                return (turn.content or "").strip()

            for tc in turn.tool_calls:
                result = self._read_file(tc.arguments.get("path", ""), root)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                tool_call_count += 1

        messages.append({
            "role": "user",
            "content": "Write the complete updated agent.md now. Start with '## Files'.",
        })
        final = self._client.call_single(
            tier=self._tier,
            messages=messages,
            max_tokens=AGENT_MD_GENERATION_MAX_TOKENS,
        )
        return (final.content or "").strip()

    # ── internal helpers ──────────────────────────────────────────────────────

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

    @staticmethod
    def _resolve_within_root(path: str, root: str) -> Path | None:
        """Return the resolved path only if it stays inside root; None otherwise."""
        root_resolved = Path(root).resolve()
        candidate = (root_resolved / path).resolve()
        try:
            candidate.relative_to(root_resolved)
            return candidate
        except ValueError:
            return None

    def _read_file(self, path: str, root: str) -> str:
        safe = self._resolve_within_root(path, root)
        if safe is None:
            return f"Access denied: {path!r} is outside the project repo"
        if not safe.is_file():
            return f"File not found: {path}"
        return safe.read_text(encoding="utf-8")
