## Files

agent_md.py — Validator for agent.md file format and structural rules
  AgentMdValidator (class) — 12-103 — Validates agent.md against format spec and collects violations
  validate (method) — 20-41 — Main validation method returning list of violation messages
agent_md_generation_agent.py — LLM agent that generates agent.md files by reading source code
  AgentMdGenerationAgent (class) — 46-179 — Reads source files via tool calling then writes agent.md
  generate (method) — 60-100 — Generate new agent.md by reading all source files in a directory
  update (method) — 102-141 — Incrementally update existing agent.md for changed files only
agent_md_generation_prompt.py — System prompt for agent.md generation with format rules and examples
  AGENT_MD_GENERATION_SYSTEM_PROMPT (constant) — 4-57 — Detailed prompt teaching format rules and providing examples
code_discovery_agent.py — LLM agent that navigates agent.md tree to find code relevant to tasks
  CodeDiscoveryAgent (class) — 54-137 — Explores repo via agent.md index to locate relevant files and symbols
  discover (method) — 64-108 — Navigate agent.md tree and return DiscoveryResult with relevant sections
code_discovery_prompt.py — System prompt for code discovery agent with tools and exploration strategy
  CODE_DISCOVERY_SYSTEM_PROMPT (constant) — 1-65 — Detailed prompt with tool definitions and path construction rules
constants.py — Configuration limits and settings for agent.md generation and discovery
file_index_service.py — High-level service orchestrating agent.md generation, validation, and discovery
  FileIndexService (class) — 15-274 — Manages agent.md generation, loading discovered sections, and incremental updates
  generate_all (method) — 21-30 — Generate agent.md for every source directory bottom-up
  load_sections (method) — 32-63 — Load source content for discovered sections respecting token budget
  update_after_task (method) — 65-117 — Incrementally update agent.md for task-affected directories
  validate_all (method) — 119-131 — Validate all agent.md files under root and return violations by path
git_utils.py — Git utilities for retrieving changed files in the working tree
  get_changed_files (function) — 5-26 — Return repo-relative paths of files changed vs HEAD
path_safety.py — Path safety utilities for repo-relative path resolution
  resolve_within_root (function) — 5-12 — Resolve path and ensure it stays within repo root boundary
