## Files

agentic_turn.py — AgenticTurn and ToolCall data structures for LLM agent interactions
  ToolCall (class) — 7-10 — Tool invocation with LLM-assigned ID, name, and arguments
  AgenticTurn (class) — 14-17 — Represents a single LLM response with optional tool calls
errors.py — LLM API error definitions
  APIError (class) — 1-2 — Exception raised when LLM API calls fail
model_client.py — LiteLLM wrapper for model completion and tool-use calls
  ModelClient (class) — 27-120 — Client for calling language models via LiteLLM with fallback support
  call (method) — 35-70 — Executes a simple completion call and returns ModelResponse
  call_single (method) — 72-120 — Completion call with optional tool use, returning AgenticTurn
model_response.py — Model completion response encapsulation
  ModelResponse (class) — 9-12 — Dataclass holding LLM content, model name, and token usage
tier.py — Tier configuration for model selection and constraints
  Tier (class) — 5-16 — Model list, retry limit, and context budget constraints
tier_config.py — Complexity-based tier configuration builder
  TierConfig (class) — 14-58 — Container for low/medium/high/orchestrator/reviewer tiers
  from_settings (method) — 22-49 — Constructs TierConfig from application settings
  for_complexity (method) — 51-58 — Selects appropriate tier by task complexity
token_counter.py — Simple token estimation utility
  TokenCounter (class) — 4-7 — Provides static token estimation from text length
