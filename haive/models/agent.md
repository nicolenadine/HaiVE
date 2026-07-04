## Files

__init__.py — Package initialization for haive models
agent_output.py — Output schemas for various agent types (scaffold, code editor, reviewers, test generator, documentation writer)
  FileToCreate (class) — 8-12 — Model for specifying new files to create
  ScaffoldAgentOutput (class) — 15-19 — Output from scaffold agent containing files and notes
  FileEdit (class) — 24-28 — Model for editing existing files with complete content
  CodeEditorOutput (class) — 31-35 — Output from code editor agents with file edits and notes
  ReviewFinding (class) — 40-47 — Finding from review agents with file, line, severity, and suggestions
  ReviewAgentOutput (class) — 50-80 — Structured review verdict with passed/uncertain/infeasible states and findings
  TestGeneratorOutput (class) — 85-89 — Output from test generator with test file edits
  DocumentationWriterOutput (class) — 94-98 — Output from documentation writer with file edits
config.py — Application configuration settings and agent configuration models
  _CsvDotEnvSource (class) — 12-24 — Custom DotEnv source supporting comma-separated list values
  Settings (class) — 27-113 — Global application configuration with LLM tiers, adapter selection, and credentials
  load_settings (function) — 116-124 — Load settings from environment and config file with error handling
  AgentConfig (class) — 127-138 — Per-agent configuration with role, prompts, tokens, and skills
context_request.py — Context request model for reviewer file read requests
  ContextRequest (class) — 8-17 — Model for reviewer requesting file context before rendering verdict
discovery.py — Repository discovery models for loading relevant source sections
  DiscoveredSection (class) — 8-14 — Metadata for a discovered repo section with file path and line range
  DiscoveryResult (class) — 17-19 — Result containing discovered sections and status
  LoadedSection (class) — 22-25 — Loaded source content for a discovered section with reason
enums.py — Task status, agent role, and complexity enumerations
  TaskStatus (class) — 4-10 — Enum of task lifecycle states (pending, in_progress, complete, blocked, skipped)
  AgentRole (class) — 13-23 — Enum of agent roles (scaffold, implementation, refactoring, reviewers, etc.)
  Complexity (class) — 26-29 — Enum of task complexity levels (low, medium, high)
orchestrator.py — Orchestrator input/output models for task coordination
  OrchestratorTaskView (class) — 9-22 — Read-only task view for orchestrator with status and verdict
  OrchestratorInput (class) — 25-32 — Input to orchestrator containing project, tasks, and comments
  NewTask (class) — 35-45 — Task specification for orchestrator to create with dependencies and criteria
  OrchestratorOutput (class) — 48-58 — Orchestrator output with new tasks and completion flag
review.py — Review verdict model bridging agent output and execution state
  ReviewVerdict (class) — 8-31 — Review verdict with passed/uncertain/infeasible states and suggestions
state.py — Project state persistence model with task execution records
  ProjectState (class) — 10-28 — Serializable project state snapshot with schema version and task records
task.py — Task, project, and execution record domain models
  Project (class) — 8-12 — Container for project metadata and branch information
  Task (class) — 15-25 — Individual task with role, complexity, dependencies, and acceptance criteria
  TaskComment (class) — 28-32 — Comment on a task with author and timestamp
  AttemptLogEntry (class) — 35-38 — Log entry tracking attempt tier and reason
  VerdictSummary (class) — 41-44 — Stored verdict summary with passed status and reason
  TokenUsage (class) — 47-50 — Token usage metrics for LLM calls
  TaskExecutionRecord (class) — 53-66 — Complete execution record with verdict, attempts, model, and metrics
verdict.py — Review verdict model (duplicate/legacy definition)
  ReviewVerdict (class) — 4-8 — Review verdict with passed and uncertain flags
