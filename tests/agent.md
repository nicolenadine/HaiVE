## Files

conftest.py — Shared pytest fixtures for test suite
test_agent_md_validator.py — Validation rules for agent.md format and content
test_agent_registry.py — Agent configuration registry loading and validation
test_cli_run.py — CLI run command orchestration and task scheduling integration
test_code_discovery_agent.py — LLM-driven code discovery and context retrieval
test_context_assembler.py — Assembly of task context from discoveries and dependencies
test_enums.py — Enumeration values and serialization for TaskStatus, AgentRole, Complexity
test_file_index_service.py — Code documentation generation, validation, and repo mapping
test_git_utils.py — Git utilities for detecting changed files in repository
test_llm.py — LLM tier configuration, model client, and token counting
test_observability.py — OpenTelemetry tracing integration and span attributes
test_orchestrator.py — Orchestrator task view building and recovery task validation
test_orchestrator_examples.py — Example selection and milestone classification for prompts
test_output_validator.py — Agent output schema validation and JSON extraction
test_pm_adapter.py — GitHub project management adapter for tasks and milestones
test_review_agent.py — Code review verdict generation and context requests
test_state_store.py — Project state persistence and concurrent merge operations
test_symbol_line_corrector.py — AST-based correction of symbol line ranges in agent.md
test_task_executor.py — Task execution with retry, escalation, and status updates
test_task_scheduler.py — Concurrent task scheduling with dependency and blocking rules
test_task_state_schemas.py — ProjectState and TaskExecutionRecord validation schemas
test_vcs_adapter.py — GitHub version control operations for branches and pull requests
