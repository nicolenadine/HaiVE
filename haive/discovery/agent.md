## Files

__init__.py — Package initialization for code discovery and agent.md generation modules
agent_md.py — Agent.md format validator with rule checking and format violation detection
  AgentMdValidator (class) — 20-123 — Validates agent.md structure against format specification
  _FILES_ENTRY_RE (constant) — 8-9 — Regex for unindented file/subdirectory entry format
  _SYMBOL_ENTRY_RE (constant) — 10-11 — Regex for 2-space indented symbol sub-entry format
agent_md_generation_agent.py — LLM-driven agent that reads files and generates agent.md content
  AgentMdGenerationAgent (class) — 124-282 — Orchestrates file reading and agent.md generation via tool calling
  generate (method) — 136-187 — Generates initial agent.md by reading all source files
  update (method) — 189-244 — Incrementally updates existing agent.md for changed files only
agent_md_generation_prompt.py — System prompt template for agent.md generation task
  AGENT_MD_GENERATION_SYSTEM_PROMPT (constant) — 4-99 — Instructs LLM on agent.md format rules and symbols
code_discovery_agent.py — LLM-driven agent that navigates agent.md tree to find relevant files and symbols
  CodeDiscoveryAgent (class) — 79-239 — Explores agent.md indices to discover code relevant to a task
  discover (method) — 92-130 — Navigates repo using read_agent_md and list_subdirectories tools
code_discovery_prompt.py — System prompt for navigating agent.md indices and discovering relevant code
  CODE_DISCOVERY_SYSTEM_PROMPT (constant) — 1-125 — Instructs LLM on exploration strategy and output format
constants.py — Configuration constants for agent.md generation and code discovery limits
  AGENT_MD_MAX_LINES (constant) — 6-6 — Maximum total line count per agent.md file
  SOURCE_EXTENSIONS (constant) — 35-56 — File extensions treated as source code
file_index_service.py — Service for generating, maintaining, and reading agent.md index tree
  FileIndexService (class) — 26-353 — Manages agent.md files for full repo indexing, updates, and loading
  generate_all (method) — 31-41 — Generates agent.md for every source directory bottom-up
  read_repo_map (method) — 43-72 — Concatenates all agent.md files into single repo map respecting token budget
  resync_line_ranges (method) — 74-97 — Re-applies AST-based line-range correction to all agent.md files
  load_sections (method) — 99-137 — Loads source content for discovered sections within token budget
  update_after_task (method) — 139-204 — Incrementally updates agent.md files for directories touched by task
  validate_all (method) — 206-222 — Validates all agent.md files under root and returns violations by path
path_safety.py — Path validation utility to prevent directory traversal outside repo root
  resolve_within_root (function) — 6-14 — Returns resolved path only if it stays inside root directory
symbol_line_corrector.py — AST-based corrector for symbol line ranges in agent.md files
  correct_line_ranges (function) — 81-130 — Fixes symbol start-end line numbers using Python AST parsing
  _collect_python_symbols (function) — 26-48 — Extracts class/function/method definitions via ast module
  _best_match (function) — 51-66 — Disambiguates duplicate symbol names by kind and distance heuristic
