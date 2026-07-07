## Files

__init__.py — Test package initialization
conftest.py — Pytest fixtures and shared test utilities
test_agent_md_validator.py — Validation rules for agent.md file format and content
  AgentMdValidator (class) — 3-8 — Pydantic validator for agent.md structure
test_agent_registry.py — Agent registry loading and orchestrator configuration
test_cli_run.py — CLI run command execution and orchestration workflow tests
  TestRunPreflightAgentMd (class) — 155-165 — Validates agent.md existence before run
  TestRunTaskCreation (class) — 232-270 — Task creation and dependency resolution in run loop
  TestReconciliation (class) — 335-374 — Merged PR detection and status updates
test_code_discovery_agent.py — Code discovery agent for locating relevant source files
  TestTargetedDiscovery (class) — 119-231 — LLM-guided file and symbol discovery
  TestGuardrailCutoff (class) — 238-266 — Tool call limit enforcement to prevent runaway
test_context_assembler.py — Context assembly for task execution prompts
  TestAssemblyOrder (class) — 33-77 — Proper ordering of task, context, and feedback sections
test_enums.py — Validation of TaskStatus, AgentRole, and Complexity enumerations
test_file_index_service.py — Repository indexing and agent.md generation service
  TestGenerateAll (class) — 52-203 — LLM-based agent.md generation with validation and retry
  TestValidateAll (class) — 208-249 — Recursive validation of agent.md files in repo
test_llm.py — LLM client, tier configuration, and token counting utilities
  TestModelClient (class) — 74-116 — LiteLLM integration with fallback models
  TestTierConfig (class) — 123-154 — Tier-based LLM configuration mapping by complexity
test_observability.py — OpenTelemetry tracing spans for run and task execution
  TestSetupObservability (class) — 42-96 — OTel setup idempotency and endpoint configuration
test_orchestrator.py — Orchestrator prompting and JSON response parsing
  TestOrchestratorRunLoop (class) — 249-359 — Wave planning, recovery tasks, and done signaling
  TestTaskViewBuilder (class) — 194-242 — Task view generation with budget-aware pruning
test_orchestrator_examples.py — Example-based milestone classification and selection
  TestExampleLibraryLoading (class) — 154-197 — YAML parsing and validation of planning examples
  TestMilestoneClassifier (class) — 204-243 — Tag-based milestone classification from text
test_output_validator.py — Agent output schema validation and JSON extraction
  TestJsonExtraction (class) — 41-87 — Robust JSON parsing from wrapped, embedded, or bare formats
  TestSchemaValidation (class) — 92-118 — Pydantic model validation with empty-list rejection
test_pm_adapter.py — GitHub project management adapter for task CRUD and field ops
  TestGetProject (class) — 131-165 — Milestone to Project conversion with derived branch names
  TestCreateTask (class) — 451-541 — GraphQL-based task creation with field value setting
test_read_file_tool.py — File reading tool for code review and context assembly
  TestReadFileForToolCall (class) — 42-63 — Path security, budget truncation, and error handling
  TestRunToolLoop (class) — 68-166 — Agentic loop with file reads, budget/round limits
test_review_agent.py — Code review verdict generation with model escalation
  TestVerdictContent (class) — 73-94 — JSON parsing and suggestion extraction from reviewers
  TestModelEscalation (class) — 99-143 — Uncertain escalation and parse-failure recovery
test_state_store.py — Project state persistence with concurrent merge safety
  TestLoadOrInit (class) — 34-61 — File creation and schema version validation on load
  TestMergeTaskRecord (class) — 89-120 — Thread-safe concurrent record updates via file merge
test_symbol_line_corrector.py — AST-based symbol location lookup and line range correction
  TestCorrectLineRanges (class) — 10-145 — Python symbol finding and line offset correction
test_task_executor.py — Task execution with retry, review, and merge handling
  TestHappyPath (class) — 148-207 — Single-attempt task completion with PR creation and merge
  TestRetry (class) — 328-391 — Reviewer feedback injection and schema-error recovery
test_task_scheduler.py — Concurrent task scheduling with dependency ordering
  TestConcurrencyCap (class) — 48-79 — MAX_EXECUTORS limit on parallel task execution
  TestBlockedPropagation (class) — 134-186 — Blocked status propagation across dependencies
test_task_state_schemas.py — ProjectState and TaskExecutionRecord schema validation
  TestProjectStateRoundTrip (class) — 44-61 — JSON serialization and deserialization invariants
  TestSchemaVersionMismatch (class) — 64-86 — Version validation with descriptive error messages
test_vcs_adapter.py — GitHub VCS adapter for branch, PR, and merge operations
  TestCreateBranch (class) — 51-108 — Remote ref creation and local checkout coordination
  TestMergePR (class) — 204-241 — Direct merge with GraphQL auto-merge fallback
