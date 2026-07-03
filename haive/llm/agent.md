## Files

agentic_turn.py — Agentic tool calls and turn completion structures
  ToolCall (class) — 8-11 — LLM-assigned tool invocation with ID, name, and arguments
  AgenticTurn (class) — 14-17 — Response turn containing tool calls and/or final content
errors.py — API error exceptions
  APIError (class) — 1-1 — Base exception for LLM API failures
model_client.py — LiteLLM-based model client with completion and agentic turn support
  ModelClient (class) — 17-119 — Wrapper around LiteLLM with single and streaming completions
  call (method) — 24-56 — Executes a model call with fallback support
  call_single (method) — 58-119 — Single LiteLLM call with optional tool use
model_response.py — Model response structure with token usage tracking
  ModelResponse (class) — 6-9 — Response from LLM containing content, model, and token counts
tier.py — Model tier configuration with attempt and context limits
  Tier (class) — 4-12 — Dataclass representing a model tier with validation
tier_config.py — Multi-tier LLM configuration management
  TierConfig (class) — 9-53 — Manages five tiers (low, medium, high, orchestrator, reviewer)
  from_settings (method) — 12-35 — Constructs TierConfig from application settings
  for_complexity (method) — 37-43 — Retrieves tier matching a task complexity level
token_counter.py — Token estimation utility
  TokenCounter (class) — 4-5 — Estimates token count by dividing text length by 4
