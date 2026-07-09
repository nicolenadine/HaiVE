## Files

__init__.py — Package initialization for haive module
cli.py — Command-line interface for config, project setup, discovery, and milestone execution
  MilestoneRunOutcome (constant) — 18-24 — Enum describing completion status of a single milestone run
  app (constant) — 26-38 — Typer CLI application with config and project subcommands
  config_app (constant) — 39-42 — Typer subcommand group for config lifecycle management
  project_app (constant) — 43-46 — Typer subcommand group for GitHub Project board setup and management
  _check_git_on_path (function) — 207-213 — Validates that git is available on PATH
  _check_active_config (function) — 216-221 — Validates that an active config can be loaded
  _resolve_milestone_id (function) — 224-234 — Resolves milestone ID from CLI flag or config fallback
  _preflight_checks (function) — 237-239 — Runs git and config availability checks
  _print_dry_run_output (function) — 244-267 — Formats and displays dry-run preview of pending tasks
  config_create (function) — 53-60 — Create a new named config
  config_use (function) — 64-71 — Activate a named config
  config_set (function) — 75-85 — Set a KEY=VALUE in the active config
  config_edit (function) — 89-91 — Open the active config in $EDITOR
  config_show (function) — 95-107 — Display the active config with masked sensitive values
  config_list (function) — 111-120 — List all named configs with active marker
  config_delete (function) — 124-131 — Delete a named config
  project_setup (function) — 137-202 — Create or configure a Haive-compatible GitHub Project v2 board
  index (function) — 273-339 — Generate or validate per-directory agent.md index files
  discover (function) — 345-411 — Run the Code Discovery Agent standalone for task-relevant code sections
  load (function) — 417-488 — Discover relevant files and print their loaded source content
  _run_milestone (function) — 493-807 — Core orchestration loop executing one milestone through waves until done or blocked
  run (function) — 811-869 — Run haive agent harness for a single project milestone
  run_all (function) — 873-972 — Work through queue of open milestones with optional checkpoint gating
  prune_branches (function) — 978-1035 — List and delete haive/task-* branches with merged PRs
adapters/ — Project management and version control system adapters for GitHub integration
config/ — Configuration management for .env-based settings and CLI config lifecycle
discovery/ — Code discovery, agent.md generation, and repo indexing for LLM context assembly
execution/ — Task execution loop with discovery, LLM calls, review, PR creation, and merge
llm/ — LiteLLM wrapper, model client, tier configuration, and agentic tool calling
models/ — Pydantic domain models for tasks, state, config, and LLM output schemas
observability/ — OpenTelemetry tracing setup and span context managers
orchestration/ — Multi-wave task planning orchestrator with example library and scheduler
persistence/ — File-based state store with locking and schema validation
registry/ — Agent configuration registry mapping roles to system prompts and schemas
resources/ — Bundled agent definitions and planning examples (agents.yaml, prompts, schemas)
