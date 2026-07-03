## Files

agent_md_spec.md — Specification for the agent.md format required for all source directories
agent_model.md — Definition of agent roles, capabilities, constraints, system prompt templates, and the roster
architecture_overview.md — Core system components, communication patterns, and execution flow with detailed diagrams
build_plan.md — Phased implementation roadmap with 24 numbered steps grouped into 11 phases with dependencies
communication_protocol.md — Inter-component data handoffs, message schemas, and what is never passed between components
data_and_state_model.md — Pydantic schema definitions for tasks, verdicts, state files, adapters, and configuration
decisions.md — Design decisions log including rationale, alternatives considered, tradeoffs, and resolved questions
future_features.md — Post-v1 features including CLI enhancements and optional GitHub native dependency API integration
hardening_backlog.md — Reliability gaps and edge cases identified during planning for v1 integration testing
model_routing_strategy.md — Complexity-to-tier mapping, retry and escalation rules, and complete model configuration
project_overview.md — Project goals, non-goals, core terminology, agent concepts, and success criteria
token_efficiency_strategy.md — Context budgets per tier, section priorities, what is included or excluded from prompts
