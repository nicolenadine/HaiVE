## Files

agent_md.py — Validator for agent.md structural format and content rules
  AgentMdValidator (class) — 20-123 — Validates agent.md against format spec
  validate (method) — 27-48 — Check file length, sections, and prose constraints
agent_md_generation_agent.py — LLM agent that generates agent.md files by reading sources
  AgentMdGenerationAgent (class) — 124-282 — Orchestrates agent.md generation via read_file tool
  generate (method) — 136-187 — Generate agent.md for a directory by reading all source files
  update (method) — 189-244 — Incrementally update agent.md for changed files only
agent_md_generation_prompt.py — System prompt template for agent.md generation
  AGENT_MD_GENERATION_SYSTEM_PROMPT (constant) — 3-73 — Instructions for writing agent.md with format rules
code_discovery_agent.py — LLM agent that navigates agent.md tree to find relevant code
  CodeDiscoveryAgent (class) — 78-211 — Explores agent.md index files to locate task-relevant files and symbols
  discover (method) — 91-129 — Navigate repo via agent.md to find files matching a task description
code_discovery_prompt.py — System prompt template for code discovery navigation
  CODE_DISCOVERY_SYSTEM_PROMPT (constant) — 1-103 — Instructions for exploring agent.md tree and selecting relevant sections
constants.py — Configuration limits and guardrails for indexing and discovery
  AGENT_MD_MAX_LINES (constant) — 4-4 — Maximum total lines per agent.md file
  AGENT_MD_MIN_DESCRIPTION_LEN (constant) — 7-7 — Minimum description character length
  AGENT_MD_MAX_DESCRIPTION_LEN (constant) — 8-8 — Maximum description character length
  AGENT_MD_PROSE_WORD_THRESHOLD (constant) — 11-13 — Word count threshold for prose paragraph detection
  SOURCE_EXTENSIONS (constant) — 27-54 — File extensions treated as indexable source code
file_index_service.py — Primary service orchestrating agent.md generation and discovery
  AgentMdGenerationError (class) — 22-23 — Raised when agent.md generation fails all retries
  FileIndexService (class) — 26-353 — Manages agent.md generation, discovery, loading, and incremental updates
  generate_all (method) — 31-41 — Generate agent.md for every source directory bottom-up
  read_repo_map (method) — 43-72 — Concatenate all agent.md files into a single repo index
  load_sections (method) — 99-137 — Load source content for discovered sections respecting token budget
  update_after_task (method) — 139-204 — Incrementally update agent.md for files changed by a task
git_utils.py — Git operations for tracking file changes
  get_changed_files (function) — 6-35 — Return repo-relative paths of files changed vs HEAD
path_safety.py — Safe path resolution preventing directory traversal
  resolve_within_root (function) — 6-14 — Resolve relative path and validate it stays within root
symbol_line_corrector.py — AST-based correction of symbol line ranges in agent.md
  correct_line_ranges (function) — 81-130 — Fix symbol start-end lines using actual Python ast parse results
  _collect_python_symbols (function) — 26-48 — Extract class/function/method definitions via ast
  _best_match (function) — 51-66 — Disambiguate symbol names by kind and proximity to guessed line
