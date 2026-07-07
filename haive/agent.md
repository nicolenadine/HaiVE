## Files

__init__.py — Package initialization for haive framework
cli.py — Command-line interface for indexing, discovering, loading, executing tasks, and managing configuration
  _check_git_on_path (function) — 85-91 — Verifies git is available on PATH
  _check_active_config (function) — 94-99 — Validates that an active config file can be loaded
  _resolve_milestone_id (function) — 102-112 — Resolves milestone ID from CLI arg or config fallback
  _preflight_checks (function) — 115-117 — Runs all preflight checks before command execution
  _print_dry_run_output (function) — 122-145 — Formats and prints orchestrator dry-run output
  config_create (function) — 18-25 — Creates a new named configuration file
  config_use (function) — 29-36 — Activates a named configuration
  config_set (function) — 40-50 — Sets a key-value pair in the active configuration
  config_edit (function) — 54-56 — Opens the active configuration in the default editor
  config_show (function) — 60-67 — Displays the active configuration with masked sensitive values
  config_list (function) — 71-80 — Lists all available configurations with active marker
  index (function) — 151-202 — Generates or validates per-directory agent.md index files
  discover (function) — 208-269 — Runs code discovery agent to find relevant code sections for a task
  load (function) — 275-341 — Combines discovery and loading to assemble context for a task
  run (function) — 347-652 — Main orchestration loop executing tasks across waves with planning and review
  prune_branches (function) — 658-715 — Deletes haive task branches whose PRs have been merged
adapters/ — Project management and version control system adapter interfaces and implementations
config/ — Configuration management for named configs and environment settings
discovery/ — Code discovery agent and agent.md file indexing service for repository navigation
execution/ — Task execution engine with LLM agent coordination, code generation, and PR workflow
llm/ — LLM provider integration with multi-tier model configurations and token counting
models/ — Pydantic data models for tasks, state, configuration, and orchestration
observability/ — OpenTelemetry tracing and instrumentation setup for distributed tracing
orchestration/ — Task orchestration engine with planning, examples, and dependency scheduling
persistence/ — State management and persistence layer for projects and task execution records
registry/ — Agent configuration registry for loading and managing agent definitions
