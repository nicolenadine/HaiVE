## Files

__init__.py — Package initialization for LLM module
agentic_turn.py — Agent response structures with tool calls and content
  ToolCall (class) — 7-10 — Tool invocation with ID, name, and parsed JSON arguments
  AgenticTurn (class) — 14-17 — Response from LLM with optional tool calls or final content
errors.py — Exception types for LLM API interactions
  APIError (class) — 1-2 — Exception raised when LiteLLM API calls fail
model_client.py — LiteLLM client wrapper for model completions and tool use
  ModelClient (class) — 27-120 — Unified interface to multiple LLM providers via LiteLLM
  call (method) — 35-70 — Single completion call with token usage tracking
  call_single (method) — 72-120 — Completion call with optional tool use support
model_response.py — Structured response from a model completion call
  ModelResponse (class) — 9-12 — Response data with content, model used, and token tracking
tier.py — Model tier definition with retry and context constraints
  Tier (class) — 5-16 — Configuration for a model tier with fallbacks and resource limits
tier_config.py — Multi-tier LLM configuration for complexity levels and roles
  TierConfig (class) — 14-58 — Factory for low/medium/high tiers plus orchestrator and reviewer
  from_settings (method) — 22-49 — Creates TierConfig from application settings
  for_complexity (method) — 51-58 — Returns appropriate tier for a given task complexity
token_counter.py — Simple token estimation utility
  TokenCounter (class) — 4-7 — Provides token count estimation based on text length
