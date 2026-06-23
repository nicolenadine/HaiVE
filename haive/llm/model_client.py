from __future__ import annotations

import litellm

from haive.llm.errors import APIError
from haive.llm.tier import Tier
from haive.models.config import Settings


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key:
            litellm.anthropic_api_key = settings.anthropic_api_key
        if settings.openai_api_key:
            litellm.openai_api_key = settings.openai_api_key

    def call(self, tier: Tier, prompt: str, system: str, max_tokens: int) -> str:
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
        return response.choices[0].message.content
