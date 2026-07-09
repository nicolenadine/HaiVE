from __future__ import annotations

import json
from dataclasses import dataclass

from haive.discovery.path_safety import resolve_within_root
from haive.llm.agentic_turn import AgenticTurn
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.llm.token_counter import TokenCounter

READ_FILE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the full content of a repo-relative file you need but were not "
            "given, to verify a claim or fill a gap in your context. Only request "
            "a file you can identify from an import, call site, or reference "
            "already visible in what you were given — do not use this to browse "
            "or explore the repo speculatively."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repo-relative file path, e.g. 'haive/models/task.py'.",
                },
                "reason": {
                    "type": "string",
                    "description": "One sentence explaining what you need to verify or why this file is needed.",
                },
            },
            "required": ["path", "reason"],
        },
    },
}


@dataclass
class ToolLoopResult:
    content: str
    model_used: str
    messages: list[dict]
    remaining_budget: int


def read_file_for_tool_call(path: str, root: str, remaining_budget: int) -> tuple[str, int]:
    """Returns (content or error text to show the model, tokens consumed)."""
    safe = resolve_within_root(path, root)
    if safe is None:
        return f"Access denied: {path!r} is outside the project repo.", 0
    if not safe.is_file():
        return f"File not found: {path}", 0

    text = safe.read_text(encoding="utf-8")
    tokens = TokenCounter.estimate(text)
    if tokens > remaining_budget:
        char_budget = remaining_budget * 4
        text = (
            f"{text[:char_budget]}\n"
            f"... [truncated: {tokens} tokens total, budget allows ~{remaining_budget}]"
        )
        tokens = remaining_budget
    return text, tokens


def _looks_like_final_answer(content: str | None) -> bool:
    """Cheap plausibility check, not full JSON validation — OutputValidator
    already owns that. Just enough to tell "the model is still reasoning
    out loud" (no brace anywhere) apart from "the model gave some form of
    answer" (worth handing to the validator, whatever the outcome).
    """
    return content is not None and "{" in content


def _assistant_message(turn: AgenticTurn) -> dict:
    msg: dict = {"role": "assistant", "content": turn.content}
    if turn.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return msg


def run_tool_loop(
    model_client: ModelClient,
    tier: Tier,
    messages: list[dict],
    max_tokens: int,
    root: str,
    budget: int,
    max_rounds: int,
) -> ToolLoopResult:
    """Runs call_single in a loop, honoring read_file tool calls, until the
    model returns a final (non-tool) response, the budget runs out, or the
    round safety valve is hit.

    Does not mutate the caller's messages list — returns an extended copy, so
    a caller that escalates across multiple models (as ReviewAgent does across
    REVIEWER_MODELS) can carry the transcript forward between calls to this
    function without the original list changing under it.
    """
    messages = list(messages)
    remaining = budget

    for _ in range(max_rounds):
        if remaining <= 0:
            messages.append({
                "role": "user",
                "content": "Context budget exhausted — you must give your final answer now, no more files can be read.",
            })
            final = model_client.call_single(tier=tier, messages=messages, max_tokens=max_tokens)
            return ToolLoopResult(
                content=final.content or "", model_used=final.model_used,
                messages=messages, remaining_budget=remaining,
            )

        turn = model_client.call_single(
            tier=tier, messages=messages, max_tokens=max_tokens, tools=[READ_FILE_TOOL],
        )
        if not turn.tool_calls:
            if _looks_like_final_answer(turn.content):
                return ToolLoopResult(
                    content=turn.content or "", model_used=turn.model_used,
                    messages=messages, remaining_budget=remaining,
                )
            # No tool call and no sign of the expected JSON answer — the
            # model is still reasoning out loud (e.g. describing its plan)
            # rather than actually done. Accepting this as final would hand
            # plain prose straight to the validator, guaranteed to fail
            # schema validation and burn a whole separate attempt (fresh
            # discovery, fresh conversation) for something recoverable
            # within this same conversation for the cost of one more turn.
            messages.append(_assistant_message(turn))
            messages.append({
                "role": "user",
                "content": "That wasn't your final answer — respond with only the JSON object described in your instructions, nothing else.",
            })
            continue

        messages.append(_assistant_message(turn))
        for tc in turn.tool_calls:
            if remaining <= 0:
                content, tokens_used = "Context budget exhausted — no more files can be read.", 0
            else:
                path = tc.arguments.get("path", "")
                content, tokens_used = read_file_for_tool_call(path, root, remaining)
            remaining -= tokens_used
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    messages.append({
        "role": "user",
        "content": "Tool call limit reached. You must give your final answer now — no more tools available.",
    })
    final = model_client.call_single(tier=tier, messages=messages, max_tokens=max_tokens)
    return ToolLoopResult(
        content=final.content or "", model_used=final.model_used,
        messages=messages, remaining_budget=remaining,
    )
