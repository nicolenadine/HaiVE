## Files

agentic_turn.py — Tool invocation and agentic loop response structures
  AgenticTurn (class) — 14-17 — Represents LLM response with optional tool calls and final content
  ToolCall (class) — 7-10 — Single tool invocation with ID, name, and parsed arguments
errors.py — Exception definitions for LLM API failures
  APIError (class) — 1-2 — Exception for LiteLLM API call failures
model_client.py — LiteLLM wrapper providing completion and agentic calls
  ModelClient (class) — 27-120 — Manages LLM interactions with fallback models and token tracking
  call (method) — 35-70 — Single completion call with fallback models and token tracking
  call_single (method) — 72-120 — Agentic call supporting tool invocations and structured responses
model_response.py — Response dataclass for LLM completion calls
  ModelResponse (class) — 9-12 — Encapsulates content, model name, and optional token usage
tier.py — Model tier configuration with constraints
  Tier (class) — 5-16 — Specifies models, retry limits, and context budget for a tier
tier_config.py — Multi-tier LLM configuration factory
  TierConfig (class) — 14-58 — Container for five model tiers mapped to task complexity
  from_settings (method) — 22-49 — Factory constructing tiers from application settings
  for_complexity (method) — 51-58 — Select tier by task complexity level
token_counter.py — Token estimation utility
  TokenCounter (class) — 4-7 — Static utility for estimating token count from text length
