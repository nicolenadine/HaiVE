from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str          # LLM-assigned call ID (must be echoed in tool result messages)
    name: str        # tool function name, e.g. "read_agent_md"
    arguments: dict  # parsed JSON arguments


@dataclass
class AgenticTurn:
    tool_calls: list[ToolCall] = field(default_factory=list)
    content: str | None = None  # present on a final (non-tool) response
    model_used: str = ""
