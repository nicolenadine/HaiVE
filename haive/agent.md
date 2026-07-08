## Files

__init__.py — Package initialization for haive module
cli.py — Command-line interface for config, project setup, discovery, and milestone execution
  MilestoneRunOutcome (constant) — 18-24 — Enum describing completion status of a single milestone run
  app (constant) — 26-38 — Typer CLI application with config and project subcommands
  config_app (constant) — 39-42 — Typer subcommand group for config lifecycle management
  project_app (constant) — 43-46 — Typer subcommand group for GitHub Project board setup and management
  _run_milestone (function) — 485-788 — Core orchestration loop executing one milestone through waves until done or blocked
  index (function) — 273-331 — Generate or validate per-directory agent.md index files
  discover (function) — 337-403 — Run Code Discovery Agent standalone for task-relevant code sections
  load (function) — 409-480 — Load discovered sections with budget-aware filtering
  run (function) — 792-850 — Run haive agent harness for a single project milestone
  run_all (function) — 854-953 — Work through queue of open milestones with optional checkpoint gating
  prune_branches (function) — 959-1016 — List and delete haive/task-* branches with merged PRs
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
