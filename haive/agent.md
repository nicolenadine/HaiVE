## Files

__init__.py — Package initialization for haive
cli.py — CLI entry point with commands for indexing, discovering, loading, and running the harness
  config_create (function) — 18-25 — Create a new named configuration
  config_use (function) — 29-36 — Activate a named configuration
  config_set (function) — 40-50 — Set a KEY=VALUE in the active configuration
  config_edit (function) — 54-56 — Open the active config in $EDITOR or nano
  config_show (function) — 60-67 — Display the active config with sensitive values masked
  config_list (function) — 71-80 — List all named configs with active marked by *
  _check_git_on_path (function) — 85-91 — Verify git is available on PATH
  _check_active_config (function) — 94-99 — Validate that an active config can be loaded
  _resolve_milestone_id (function) — 102-112 — Resolve milestone ID from CLI arg or config
  _preflight_checks (function) — 115-117 — Run all required preflight checks before main commands
  _print_dry_run_output (function) — 122-145 — Format and display orchestrator dry-run output
  index (function) — 151-202 — Generate or validate per-directory agent.md index files
  discover (function) — 208-269 — Run Code Discovery Agent to find relevant files for a task
  load (function) — 275-341 — Discover relevant files and load their source content
  run (function) — 347-598 — Execute haive harness for a project milestone across waves
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
