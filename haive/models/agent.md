## Files

__init__.py — Package initialization for Pydantic data models
agent_output.py — Output schemas for agent-based workflow tasks (scaffold, code, review, testing, documentation)
  FileToCreate (class) — 7-10 — File creation request with path and content
  ScaffoldAgentOutput (class) — 13-18 — Scaffold agent output containing files to create and reviewer notes
  FileEdit (class) — 21-26 — File editing request with path and new content
  CodeEditorOutput (class) — 29-34 — Code editor output containing file edits and reviewer notes
  ReviewFinding (class) — 37-47 — Individual finding from a code review with severity and suggestion
  ReviewAgentOutput (class) — 50-66 — Review agent output with pass/fail verdict, findings, and summary
  TestGeneratorOutput (class) — 69-73 — Test generator output containing test file edits
  DocumentationWriterOutput (class) — 76-80 — Documentation writer output containing documentation edits
config.py — Application settings and agent configuration models
  Settings (class) — 25-113 — Main application configuration with model tier settings, API keys, and runtime flags
  load_settings (function) — 115-122 — Loads and validates Settings from environment and config files
  AgentConfig (class) — 125-134 — Individual agent configuration with role, skills, and token limits
context_request.py — Context request model for reviewer file loading queries
  ContextRequest (class) — 5-12 — Reviewer action requesting to read a file before rendering verdict
discovery.py — Models for code discovery and context loading
  DiscoveredSection (class) — 5-13 — Discovered file section with location and relevance reason
  DiscoveryResult (class) — 16-20 — Result of discovery with list of sections and status
  LoadedSection (class) — 23-28 — Loaded file content or line-range slice with reason
enums.py — Task status, agent role, and complexity level enumerations
  TaskStatus (constant) — 4-10 — Enum of task lifecycle states from pending to skipped
  AgentRole (constant) — 13-24 — Enum of available agent roles in the workflow
  Complexity (constant) — 27-30 — Enum of task complexity levels: low, medium, high
orchestrator.py — Orchestrator models for task coordination and workflow management
  OrchestratorTaskView (class) — 10-22 — Task view for orchestrator with status and execution details
  OrchestratorInput (class) — 25-31 — Orchestrator input containing project, tasks, comments, and summary
  NewTask (class) — 34-45 — New task to be created with dependencies and acceptance criteria
  OrchestratorOutput (class) — 48-57 — Orchestrator output with new tasks and completion flag
review.py — Review verdict model for code review outcomes
  ReviewVerdict (class) — 5-22 — Review verdict with pass/fail status, reason, suggestions, and uncertainty
state.py — Project state schema and execution history tracking
  ProjectState (class) — 9-25 — Serializable project state snapshot with task execution records and timestamps
task.py — Core task and project domain models with execution tracking
  Project (class) — 8-13 — Project container with ID, title, description, and branch
  Task (class) — 16-27 — Task unit of work with dependencies, complexity, and acceptance criteria
  TaskComment (class) — 30-35 — Task comment with author, body, and timestamp
  AttemptLogEntry (class) — 38-42 — Log entry tracking a single task attempt with tier and reason
  VerdictSummary (class) — 45-49 — Compact verdict snapshot with pass/fail and reason
  TokenUsage (class) — 52-57 — Token consumption metrics for model calls
  TaskExecutionRecord (class) — 60-76 — Complete execution history for a task including verdict, attempts, and timing
verdict.py — Alternative verdict model definitions
  ReviewVerdict (class) — 4-9 — Simple review verdict with pass/fail, reason, suggestions, and uncertainty flag
