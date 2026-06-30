from __future__ import annotations

import os

import litellm

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
