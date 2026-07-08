## Files

agent_md_spec.md — Format specification for per-directory agent.md index files, validator behavior, and complete valid examples
agent_model.md — Agent definitions, system prompt template, roster of 10 specialized agents, initial registry structure
architecture_overview.md — System architecture, component interactions, data flows, task lifecycle, and configuration
build_plan.md — 24-step phased implementation plan from foundation through CLI and integration testing
communication_protocol.md — Inter-component handoff formats, data contracts, and reasoning traces across every system boundary
data_and_state_model.md — Pydantic schemas for all domain objects, orchestrator I/O, agent outputs, and state persistence
decisions.md — Design decisions log with rationale, alternatives, and tradeoffs for 30+ major choices
future_features.md — Post-v1 improvements including token-efficient agent output and reviewer repo navigation
hardening_backlog.md — 10 reliability issues deferred from implementation steps, with context and remediation guidance
model_routing_strategy.md — Complexity-to-tier mapping, retry/escalation rules, and complete .env configuration reference
project_overview.md — Project mission, core design principles, build phases, success criteria, and initial open questions
token_efficiency_strategy.md — Context budgets per tier, priority allocation, code context rules, and orchestrator trimming logic
