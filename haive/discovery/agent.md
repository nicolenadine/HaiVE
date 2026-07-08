## Files

agent_md.py — agent.md format validation with section and entry parsing
  AgentMdValidator (class) — 20-123 — Validates agent.md structural format and collects violations
agent_md_generation_agent.py — LLM-based agent.md generation with tool-assisted file reading
  AgentMdGenerationAgent (class) — 124-282 — Reads source files via tools and generates or updates agent.md
agent_md_generation_prompt.py — System prompt for agent.md generation with format rules
code_discovery_agent.py — LLM agent navigating agent.md tree to find task-relevant code
  CodeDiscoveryAgent (class) — 79-239 — Discovers relevant files and symbols by exploring agent.md index
code_discovery_prompt.py — System prompt for code discovery with navigation strategy
constants.py — Tunable configuration for agent.md limits and discovery parameters
  SOURCE_EXTENSIONS (constant) — 45-65 — Frozenset of file extensions treated as source
file_index_service.py — Orchestrates agent.md generation, discovery, and validation across repo
  FileIndexService (class) — 26-353 — Manages generation, discovery, and syncing of agent.md tree
  AgentMdGenerationError (class) — 22-23 — Raised when agent.md generation fails validation
path_safety.py — Ensures repo-relative paths cannot traverse outside root
  resolve_within_root (function) — 6-14 — Validates and resolves path staying within root
symbol_line_corrector.py — AST-based correction of symbol line ranges in agent.md
  correct_line_ranges (function) — 81-130 — Corrects symbol line numbers using real Python AST
