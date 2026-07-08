## Files

__init__.py — Package initialization for haive framework
cli.py — Command-line interface for indexing, discovering, loading, executing tasks, and managing configuration
  config_create (function) — 29-36 — Creates a new named configuration file
  config_use (function) — 40-47 — Activates a named configuration
  config_set (function) — 51-61 — Sets a key-value pair in the active configuration
  config_edit (function) — 65-67 — Opens the active configuration in the default editor
  config_show (function) — 71-83 — Displays the active configuration with masked sensitive values
  config_list (function) — 87-96 — Lists all available configurations with active marker
  config_delete (function) — 100-107 — Deletes a named configuration
  project_setup (function) — 113-178 — Creates or configures a Haive-compatible GitHub Project v2 board
  _check_git_on_path (function) — 183-189 — Verifies git is available on PATH
  _check_active_config (function) — 192-197 — Validates that an active config file can be loaded
  _resolve_milestone_id (function) — 200-210 — Resolves milestone ID from CLI arg or config fallback
  _preflight_checks (function) — 213-215 — Runs all preflight checks before command execution
  _print_dry_run_output (function) — 220-243 — Formats and prints orchestrator dry-run output
  index (function) — 249-307 — Generates or validates per-directory agent.md index files
  discover (function) — 313-379 — Runs code discovery agent to find relevant code sections for a task
  load (function) — 385-456 — Combines discovery and loading to assemble context for a task
  run (function) — 462-785 — Main orchestration loop executing tasks across waves with planning and review
  prune_branches (function) — 791-848 — Deletes haive task branches whose PRs have been merged
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
