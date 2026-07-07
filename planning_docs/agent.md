## Files

agent_md_spec.md — Exact format specification for `agent.md` index files, section headers, file entries, symbol sub-entries, and validation rules
agent_model.md — Agent role definitions, responsibilities, system prompt templates, and roster of 10 specialized agents
architecture_overview.md — Core system components, their data flows, lifecycle, adapters, service layer, and observable spans
build_plan.md — Implementation roadmap in 24 steps across 11 phases, with dependencies, success criteria, and hardening backlog
communication_protocol.md — Data handoff formats between orchestrator, executor, reviewer, adapters, and services across the full task lifecycle
data_and_state_model.md — Pydantic schemas for tasks, verdicts, context packs, agent outputs, configuration, state files, and GitHub metadata
decisions.md — Resolved design choices including tradeoffs, rationale, and superseded decisions (repo map, refactoring scope, discovery agents)
future_features.md — Post-v1 improvements including CLI enhancements, token-efficient partial edits, and symbol-line correction for non-Python
hardening_backlog.md — 10 known reliability gaps to address before integration testing (permissions, partial creation, field pagination, etc)
model_routing_strategy.md — Tier definitions, complexity-to-tier mapping, retry/escalation flow, LiteLLM configuration, and `.env` reference
project_overview.md — Project goals, non-goals, core concepts, design principles, success criteria, and initial brief from stakeholder
token_efficiency_strategy.md — Context budgets per tier, priority-ordered section allocation, code context inclusion rules, and orchestrator compression
