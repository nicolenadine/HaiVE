## Files

__init__.py — Package marker for tests
conftest.py — Shared pytest fixtures for test infrastructure setup
test_agent_md_validator.py — Agent.md format validation with format rules and line limits
  TestValidContent (class) — 37-50 — Tests for valid agent.md files
  TestFilesEntryFormat (class) — 80-116 — Tests for Files section entries and descriptions
  TestSymbolEntryFormat (class) — 119-185 — Tests for symbol entries with kinds and line ranges
test_agent_registry.py — Tests for agent registry loading and orchestrator summary generation
  TestLoad (class) — 28-79 — Tests for loading agents from YAML and field resolution
test_board_setup.py — Tests for GitHub project board setup and verification
  TestFindOrCreateProject (class) — 46-100 — Tests for project creation or reuse
test_cli_run.py — CLI run command tests including waves, reconciliation, and dry-run modes
  TestRunPreflightAgentMd (class) — 186-196 — Tests for preflight agent.md existence check
test_code_discovery_agent.py — Tests for code discovery LLM agent finding relevant files
  TestTargetedDiscovery (class) — 119-231 — Tests for navigating agent.md hierarchy
test_config_manager.py — Tests for configuration file template and value management
  TestCreate (class) — 19-38 — Tests for config template generation
test_context_assembler.py — Tests for assembling task context with sections and feedback
  TestAssemblyOrder (class) — 33-77 — Tests for section ordering in assembled context
test_enums.py — Tests for TaskStatus, AgentRole, and Complexity enumerations
test_file_index_service.py — Tests for agent.md generation and line range correction
  TestGenerateAll (class) — 52-203 — Tests for generating agent.md for source directories
test_llm.py — Tests for LLM client, model response, and tier configuration
  TestTier (class) — 56-67 — Tests for tier validation with model and budget constraints
test_observability.py — Tests for OpenTelemetry setup and span creation
  TestSetupObservability (class) — 42-96 — Tests for observability initialization
test_orchestrator.py — Tests for orchestrator run loop and task view building
  TestOrchestratorRunLoop (class) — 249-359 — Tests for orchestrator execution with recovery
test_orchestrator_examples.py — Tests for example library, classification, and selection
  TestExampleLibraryLoading (class) — 154-197 — Tests for example YAML loading and validation
test_output_validator.py — Tests for agent output schema validation and error handling
  TestJsonExtraction (class) — 41-87 — Tests for JSON parsing from various formats
test_pm_adapter.py — Tests for GitHub project management adapter integration
  TestGetProject (class) — 131-195 — Tests for project retrieval and checkpoint parsing
test_read_file_tool.py — Tests for file reading tool and agentic tool loop execution
  TestReadFileForToolCall (class) — 42-63 — Tests for safe file reading with budget
test_review_agent.py — Tests for code review agent with escalation and tool integration
  TestVerdictContent (class) — 73-94 — Tests for review verdict generation
test_state_store.py — Tests for project state persistence and concurrent writes
  TestLoadOrInit (class) — 34-61 — Tests for state file creation and schema validation
test_symbol_line_corrector.py — Tests for correcting symbol line ranges via AST analysis
  TestCorrectLineRanges (class) — 10-145 — Tests for detecting and fixing wrong symbol ranges
test_task_executor.py — Tests for task execution with retry, tier escalation, and merge
  TestHappyPath (class) — 148-207 — Tests for successful task execution and PR creation
test_task_scheduler.py — Tests for task concurrency, dependency ordering, and blocking
  TestConcurrencyCap (class) — 48-79 — Tests for enforcing maximum concurrent executors
test_task_state_schemas.py — Tests for ProjectState serialization and schema constraints
  TestProjectStateRoundTrip (class) — 44-61 — Tests for state JSON serialization
test_vcs_adapter.py — Tests for GitHub version control adapter commands
  TestCreateBranch (class) — 51-108 — Tests for branch creation from base SHA
