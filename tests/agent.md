## Files

__init__.py — Package marker for tests directory
conftest.py — Pytest configuration and shared fixtures
test_agent_md_validator.py — Agent.md format validation and violation detection tests
test_agent_registry.py — Registry loading and agent configuration tests
test_cli_run.py — CLI run command integration tests with mocked dependencies
test_code_discovery_agent.py — Code discovery agent and tool execution tests
test_context_assembler.py — Task context assembly and section ordering tests
test_enums.py — Enumeration validation and serialization tests
test_file_index_service.py — Agent.md generation, validation, and file loading tests
test_git_utils.py — Git repository utilities for detecting changed files
test_llm.py — LLM client, tier configuration, and token counting tests
test_observability.py — OpenTelemetry span setup and observability instrumentation
test_orchestrator.py — Orchestrator run loop and task view building tests
test_orchestrator_examples.py — Example library loading, classification, and selection tests
test_output_validator.py — Agent output validation and schema enforcement tests
test_pm_adapter.py — GitHub PM adapter field mapping and task lifecycle operations
test_review_agent.py — Code review agent verdict generation and context requests
test_state_store.py — Project state persistence and concurrent write handling
test_task_executor.py — Task execution, retry logic, and tier escalation tests
test_task_scheduler.py — Task scheduling with dependency ordering and concurrency limits
test_task_state_schemas.py — Task state model validation and schema version checking
test_vcs_adapter.py — GitHub VCS adapter branch, PR, and commit operations
