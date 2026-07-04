## Files

agent_md_spec.md — Structural format specification and validator rules for per-directory index files
agent_model.md — Agent role definitions, system prompt template, and initial roster of ten specialized agents
architecture_overview.md — System components, core design principle (orchestrator + disposable workers), and full component descriptions
build_plan.md — Phased implementation roadmap with 24 steps grouped into 11 phases, dependency analysis, and hardening backlog items
communication_protocol.md — Inter-component data contracts and handoff formats for all system boundaries
data_and_state_model.md — Pydantic schemas for tasks, verdicts, context packs, orchestrator I/O, and local state persistence
decisions.md — Design decision log covering configuration, stack, architecture, agent model, and special rules
future_features.md — Post-v1 enhancements: CLI usability, token optimization, and GitHub API improvements
hardening_backlog.md — Ten reliability gaps identified during review: subprocess safety, field validation, permissions, and invariants
model_routing_strategy.md — Complexity-to-tier mapping, retry and escalation logic, LiteLLM configuration, and env reference
project_overview.md — Project summary, core goals, system concept, agent model, token efficiency priorities, and initial open questions
token_efficiency_strategy.md — Context budget model, per-section allocation, code context rules, and enforcement points
