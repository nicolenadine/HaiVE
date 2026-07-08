## Files

__init__.py — Package initialization for haive framework
cli.py — Command-line interface for indexing, discovering, loading, executing tasks, and managing configuration
  config_create (function) — 21-28 — Creates a new named configuration file
  config_use (function) — 32-39 — Activates a named configuration
  config_set (function) — 43-53 — Sets a key-value pair in the active configuration
  config_edit (function) — 57-59 — Opens the active configuration in the default editor
  config_show (function) — 63-75 — Displays the active configuration with masked sensitive values
  config_list (function) — 79-88 — Lists all available configurations with active marker
  config_delete (function) — 92-99 — Deletes a named configuration
  project_setup (function) — 105-170 — Creates or configures a Haive-compatible GitHub Project v2 board
  _check_git_on_path (function) — 175-181 — Verifies git is available on PATH
  _check_active_config (function) — 184-189 — Validates that an active config file can be loaded
  _resolve_milestone_id (function) — 192-202 — Resolves milestone ID from CLI arg or config fallback
  _preflight_checks (function) — 205-207 — Runs all preflight checks before command execution
  _print_dry_run_output (function) — 212-235 — Formats and prints orchestrator dry-run output
  index (function) — 241-292 — Generates or validates per-directory agent.md index files
  discover (function) — 298-359 — Runs code discovery agent to find relevant code sections for a task
  load (function) — 365-431 — Combines discovery and loading to assemble context for a task
  run (function) — 437-749 — Main orchestration loop executing tasks across waves with planning and review
  prune_branches (function) — 755-812 — Deletes haive task branches whose PRs have been merged
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
