## Files

__init__.py — Package initialization for haive framework
cli.py — Command-line interface for indexing, discovering, loading, executing tasks, and managing configuration
  MilestoneRunOutcome (class) — 13-25 — Enum capturing the result state from a single milestone run
  config_create (function) — 49-56 — Creates a new named configuration file
  config_use (function) — 60-67 — Activates a named configuration
  config_set (function) — 71-81 — Sets a key-value pair in the active configuration
  config_edit (function) — 85-87 — Opens the active configuration in the default editor
  config_show (function) — 91-103 — Displays the active configuration with masked sensitive values
  config_list (function) — 107-116 — Lists all available configurations with active marker
  config_delete (function) — 120-127 — Deletes a named configuration
  project_setup (function) — 133-198 — Creates or configures a Haive-compatible GitHub Project v2 board
  _check_git_on_path (function) — 203-209 — Verifies git is available on PATH
  _check_active_config (function) — 212-217 — Validates that an active config file can be loaded
  _resolve_milestone_id (function) — 220-230 — Resolves milestone ID from CLI arg or config fallback
  _preflight_checks (function) — 233-235 — Runs all preflight checks before command execution
  _print_dry_run_output (function) — 240-263 — Formats and prints orchestrator dry-run output
  index (function) — 269-327 — Generates or validates per-directory agent.md index files
  discover (function) — 333-399 — Runs code discovery agent to find relevant code sections for a task
  load (function) — 405-476 — Combines discovery and loading to assemble context for a task
  _run_milestone (function) — 481-781 — Orchestrates a single milestone through completion or gating
  run (function) — 785-843 — Main loop executing tasks across waves for a single milestone
  run_all (function) — 847-946 — Works through open milestones in order with checkpoint gating
  prune_branches (function) — 952-1009 — Deletes haive task branches whose PRs have been merged
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
