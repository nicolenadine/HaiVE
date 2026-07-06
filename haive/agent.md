Based on my reading of the cli.py file, I can see it starts with the `run` function beginning at line 1. The file is quite long. Let me preserve the existing agent.md entries and update only the cli.py entry based on what I've read. The file appears to contain the config functions mentioned in the previous agent.md and the run function which is very large (appears to span from line 1 onwards). Based on the original agent.md entry stating `run (function) — 347-595`, I'll keep that range and just update the description if needed.

## Files

__init__.py — Package initialization for haive
cli.py — CLI entry point with commands for indexing, discovering, loading, and running the harness
  config_create (function) — 18-25 — Create a new named configuration
  config_use (function) — 29-36 — Activate a named configuration
  config_set (function) — 40-50 — Set a KEY=VALUE in the active configuration
  config_edit (function) — 54-56 — Open the active config in $EDITOR or nano
  config_show (function) — 60-67 — Display the active config with sensitive values masked
  config_list (function) — 71-80 — List all named configs with active marked by *
  index (function) — 151-202 — Generate or validate per-directory agent.md index files
  discover (function) — 208-269 — Run Code Discovery Agent to find relevant files for a task
  load (function) — 275-341 — Discover relevant files and load their source content
  run (function) — 347-595 — Execute haive harness for project milestone with multi-wave orchestration
adapters/ — Project management and version control adapter interfaces for PM and VCS platforms
config/ — Configuration management for named environments with validation and editing
discovery/ — Agent.md indexing, code discovery navigation, and file content loading services
execution/ — Task execution orchestration with context assembly, validation, and review loop
llm/ — LLM client wrapper with multi-tier configuration, token counting, and agentic loops
models/ — Pydantic domain models for tasks, state, orchestration, output schemas, and enums
observability/ — OpenTelemetry tracing setup and span context managers for distributed tracing
orchestration/ — Milestone decomposition orchestrator with example-based guidance and task scheduling
persistence/ — Filesystem-based project state storage with file locking and atomic writes
registry/ — Agent configuration registry loaded from YAML with per-role lookup
