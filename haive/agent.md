## Files

__init__.py — Package initialization (empty)
cli.py — Command-line interface for haive agent harness with config, indexing, discovery, and execution commands
  index (function) — 206-258 — Generates or validates per-directory agent.md index files
  discover (function) — 261-319 — Runs Code Discovery Agent to find relevant code sections for a task
  load (function) — 322-401 — Discovers relevant files and loads their full source content with token budget
  run (function) — 404-637 — Executes haive agent harness wave for a project milestone with orchestration and task execution
adapters/ — Project management and version control system adapters with GitHub integration
config/ — Configuration management across named profiles with .env support
discovery/ — Code discovery agent and agent.md file indexing with LLM-based generation and validation
execution/ — Task execution orchestration with LLM calls, output validation, code review, and PR workflows
llm/ — LiteLLM-based model client with multi-tier configuration and agentic tool calling support
models/ — Pydantic domain models for tasks, projects, agents, state, and workflow enumerations
observability/ — OpenTelemetry and LiteLLM instrumentation for distributed tracing
orchestration/ — Task planning orchestrator with example library, scheduler, and dependency management
persistence/ — Thread-safe state persistence layer with locking and schema versioning
registry/ — Agent configuration registry for managing YAML-based agent definitions and skills
