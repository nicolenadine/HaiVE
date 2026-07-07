## Files

__init__.py — Package initialization for haive framework
cli.py — Command-line interface for indexing, discovering, loading, executing tasks, and managing configuration
  config_create (function) — 18-25 — Creates a new named configuration file
  config_use (function) — 29-36 — Activates a named configuration
  config_set (function) — 40-50 — Sets a key-value pair in the active configuration
  config_edit (function) — 54-56 — Opens the active configuration in the default editor
  config_show (function) — 60-67 — Displays the active configuration with masked sensitive values
  config_list (function) — 71-80 — Lists all available configurations with active marker
  index (function) — 151-202 — Generates or validates per-directory agent.md index files
  discover (function) — 208-269 — Runs code discovery agent to find relevant code sections for a task
  load (function) — 275-341 — Combines discovery and loading to assemble context for a task
  run (function) — 347-634 — Main orchestration loop executing tasks across waves with planning and review
  prune_branches (function) — 640-697 — Deletes haive task branches whose PRs have been merged
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
