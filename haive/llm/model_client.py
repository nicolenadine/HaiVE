from __future__ import annotations

import json
import logging
import os
import warnings

import litellm

# LiteLLM's LoggingWorker creates asyncio tasks that are never awaited when
# using synchronous completion. Two suppression paths are needed:
# 1. warnings.filterwarnings for RuntimeWarnings emitted via Python's warnings module
# 2. logging.getLogger("asyncio") for "Task was destroyed" which goes through
#    asyncio's logger, not through warnings
warnings.filterwarnings("ignore", message="coroutine .* was never awaited", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="Enable tracemalloc", category=RuntimeWarning)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

from haive.llm.agentic_turn import AgenticTurn, ToolCall
from haive.llm.errors import APIError
from haive.llm.model_response import ModelResponse
from haive.llm.tier import Tier
from haive.models.config import Settings
from haive.models.task import TokenUsage


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        litellm.callbacks = []

    def call(self, tier: Tier, prompt: str, system: str, max_tokens: int) -> ModelResponse:
        primary = tier.models[0]
        fallbacks = tier.models[1:] or None
        try:
            response = litellm.completion(
                model=primary,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=max_tokens,
                fallbacks=fallbacks,
                num_retries=0,
            )
        except Exception as e:
            raise APIError(f"LiteLLM call failed ({type(e).__name__}): {e}") from e

        if not response.choices or response.choices[0].message.content is None:
            raise APIError("LiteLLM returned an empty or malformed response.")

        content = response.choices[0].message.content
        model_used = getattr(response, "model", None) or primary

        token_usage: TokenUsage | None = None
        usage = getattr(response, "usage", None)
        if usage:
            try:
                token_usage = TokenUsage(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                )
            except (AttributeError, TypeError):
                pass

        return ModelResponse(content=content, model_used=model_used, token_usage=token_usage)

    def call_single(
        self,
        tier: Tier,
        messages: list[dict],
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> AgenticTurn:
        """Single LiteLLM call supporting optional tool use.

        Returns an AgenticTurn whose tool_calls list is non-empty when the LLM
        wants to invoke tools, or whose content is set when it has a final answer.
        """
        primary = tier.models[0]
        fallbacks = tier.models[1:] or None
        kwargs: dict = dict(
            model=primary,
            messages=messages,
            max_tokens=max_tokens,
            fallbacks=fallbacks,
            num_retries=0,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            response = litellm.completion(**kwargs)
        except Exception as e:
            raise APIError(f"LiteLLM call failed ({type(e).__name__}): {e}") from e

        if not response.choices:
            raise APIError("LiteLLM returned an empty response.")

        message = response.choices[0].message
        model_used = getattr(response, "model", None) or primary

        tool_calls: list[ToolCall] = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return AgenticTurn(
            tool_calls=tool_calls,
            content=message.content,
            model_used=model_used,
        )
