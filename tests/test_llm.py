from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from haive.llm.errors import APIError
from haive.llm.model_client import ModelClient
from haive.llm.model_response import ModelResponse
from haive.llm.tier import Tier
from haive.llm.tier_config import TierConfig
from haive.llm.token_counter import TokenCounter
from haive.models.enums import Complexity


def _make_tier(models: list[str] | None = None) -> Tier:
    return Tier(
        models=models or ["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"],
        max_attempts=2,
        context_budget=8000,
    )


def _make_settings(**overrides):
    s = MagicMock()
    s.anthropic_api_key = overrides.get("anthropic_api_key", None)
    s.openai_api_key = overrides.get("openai_api_key", None)
    s.orchestrator_model = overrides.get("orchestrator_model", "orchestrator-model")
    s.reviewer_models = overrides.get("reviewer_models", ["reviewer-model"])
    s.tier_low_models = overrides.get("tier_low_models", ["low-model"])
    s.tier_low_max_attempts = overrides.get("tier_low_max_attempts", 2)
    s.tier_low_context_budget = overrides.get("tier_low_context_budget", 8000)
    s.tier_medium_models = overrides.get("tier_medium_models", ["medium-model"])
    s.tier_medium_max_attempts = overrides.get("tier_medium_max_attempts", 3)
    s.tier_medium_context_budget = overrides.get("tier_medium_context_budget", 16000)
    s.tier_high_models = overrides.get("tier_high_models", ["high-model-a", "high-model-b"])
    s.tier_high_max_attempts = overrides.get("tier_high_max_attempts", 4)
    s.tier_high_context_budget = overrides.get("tier_high_context_budget", 32000)
    return s


def _mock_response(content: str = "ok", model: str = "openai/gpt-4o") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = None
    return resp


# ---------------------------------------------------------------------------
# TestTier
# ---------------------------------------------------------------------------

class TestTier:
    def test_empty_models_raises(self):
        with pytest.raises(ValueError, match="at least one model"):
            Tier(models=[], max_attempts=1, context_budget=100)

    def test_zero_max_attempts_raises(self):
        with pytest.raises(ValueError, match="max_attempts"):
            Tier(models=["m"], max_attempts=0, context_budget=100)

    def test_zero_context_budget_raises(self):
        with pytest.raises(ValueError, match="context_budget"):
            Tier(models=["m"], max_attempts=1, context_budget=0)


# ---------------------------------------------------------------------------
# TestModelClient
# ---------------------------------------------------------------------------

class TestModelClient:
    def _client(self):
        return ModelClient(_make_settings())

    def test_call_uses_primary_model(self):
        tier = _make_tier(["model-a", "model-b"])
        with patch("litellm.completion", return_value=_mock_response()) as mock_completion:
            self._client().call(tier, "hi", "system", 100)
        assert mock_completion.call_args.kwargs["model"] == "model-a"

    def test_call_passes_fallbacks_to_litellm(self):
        tier = _make_tier(["model-a", "model-b", "model-c"])
        with patch("litellm.completion", return_value=_mock_response()) as mock_completion:
            self._client().call(tier, "hi", "system", 100)
        assert mock_completion.call_args.kwargs["fallbacks"] == ["model-b", "model-c"]

    def test_call_passes_none_for_single_model_tier(self):
        tier = _make_tier(["only-model"])
        with patch("litellm.completion", return_value=_mock_response()) as mock_completion:
            self._client().call(tier, "hi", "system", 100)
        assert mock_completion.call_args.kwargs["fallbacks"] is None

    def test_call_returns_model_response(self):
        tier = _make_tier(["model-x"])
        with patch("litellm.completion", return_value=_mock_response("hello", "model-x")):
            result = self._client().call(tier, "hi", "system", 100)
        assert isinstance(result, ModelResponse)
        assert result.content == "hello"
        assert result.model_used == "model-x"

    def test_call_raises_api_error_when_litellm_raises(self):
        tier = _make_tier()
        with patch("litellm.completion", side_effect=Exception("rate limit")):
            with pytest.raises(APIError, match="Exception"):
                self._client().call(tier, "hi", "system", 100)

    def test_call_raises_api_error_on_empty_response(self):
        tier = _make_tier()
        empty_resp = MagicMock()
        empty_resp.choices = []
        with patch("litellm.completion", return_value=empty_resp):
            with pytest.raises(APIError, match="empty or malformed"):
                self._client().call(tier, "hi", "system", 100)


# ---------------------------------------------------------------------------
# TestTierConfig
# ---------------------------------------------------------------------------

class TestTierConfig:
    def test_maps_all_fields_for_task_tiers(self):
        settings = _make_settings()
        config = TierConfig.from_settings(settings)

        assert config.low.models == ["low-model"]
        assert config.low.max_attempts == 2
        assert config.low.context_budget == 8000

        assert config.medium.models == ["medium-model"]
        assert config.medium.max_attempts == 3
        assert config.medium.context_budget == 16000

        assert config.high.models == ["high-model-a", "high-model-b"]
        assert config.high.max_attempts == 4
        assert config.high.context_budget == 32000

    def test_orchestrator_tier_wraps_single_model(self):
        config = TierConfig.from_settings(_make_settings())
        assert config.orchestrator.models == ["orchestrator-model"]
        assert config.orchestrator.max_attempts == 1

    def test_reviewer_tier_uses_reviewer_models(self):
        config = TierConfig.from_settings(_make_settings())
        assert config.reviewer.models == ["reviewer-model"]
        assert config.reviewer.max_attempts == 1

    def test_for_complexity_returns_correct_tier(self):
        config = TierConfig.from_settings(_make_settings())
        assert config.for_complexity(Complexity.LOW) is config.low
        assert config.for_complexity(Complexity.MEDIUM) is config.medium
        assert config.for_complexity(Complexity.HIGH) is config.high


# ---------------------------------------------------------------------------
# TestTokenCounter
# ---------------------------------------------------------------------------

class TestTokenCounter:
    def test_estimate(self):
        assert TokenCounter.estimate("hello world") == 3  # ceil(11/4)
        assert TokenCounter.estimate("") == 0
        assert TokenCounter.estimate("a") == 1            # ceil(1/4)

    def test_has_no_llm_imports(self):
        src = (Path(__file__).resolve().parents[1] / "haive" / "llm" / "token_counter.py").read_text()
        assert "litellm" not in src
        assert "tiktoken" not in src
