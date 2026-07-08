## Files

__init__.py — Package initialization for Haive data models
agent_output.py — Output schemas for scaffold, code editor, review, and test generator agents
  FileToCreate (class) — 8-12 — Represents a file to create with path and content
  ScaffoldAgentOutput (class) — 15-19 — Scaffold agent output with files to create and notes
  FileEdit (class) — 24-28 — Represents a file to edit with complete new content
  CodeEditorOutput (class) — 31-35 — Code editor output with file edits and reviewer notes
  ReviewFinding (class) — 40-47 — Individual finding from review with file, line, severity and message
  ReviewAgentOutput (class) — 50-80 — Review verdict with passed/uncertain/infeasible flags and findings
  TestGeneratorOutput (class) — 85-89 — Test generator output for writing or updating test files
  DocumentationWriterOutput (class) — 94-98 — Documentation writer output for documentation files
config.py — Runtime settings and agent configuration models
  Settings (class) — 27-114 — Application settings with tier-specific models, context budgets, and GitHub integration
  load_settings (function) — 117-125 — Load Settings from environment variables and config file
  AgentConfig (class) — 128-139 — Configuration for individual agents with role, skills, and constraints
discovery.py — Models for code discovery and section loading
  DiscoveredSection (class) — 8-14 — Discovered code section with file, symbol, and line ranges
  DiscoveryResult (class) — 17-19 — Result of discovery with sections list and status
  LoadedSection (class) — 22-25 — Loaded source code section with content and reason
enums.py — Task, agent, and complexity enumerations
  TaskStatus (class) — 4-11 — Task lifecycle states from pending to skipped
  AgentRole (class) — 14-24 — Roles for agents including scaffold, implementation, and review
  Complexity (class) — 27-30 — Task complexity levels: low, medium, high
orchestrator.py — Orchestrator input/output models for task coordination
  OrchestratorTaskView (class) — 9-22 — Task view for orchestrator with status and verdict info
  OrchestratorInput (class) — 25-32 — Orchestrator input with project, tasks, and comments
  NewTask (class) — 35-45 — New task specification with role, complexity, and criteria
  OrchestratorOutput (class) — 48-58 — Orchestrator output with new tasks and completion flag
review.py — Review verdict model for code review outcomes
  ReviewVerdict (class) — 8-31 — Review verdict with passed flag, reason, and suggestions
state.py — Project state model for persisting task execution records
  ProjectState (class) — 10-28 — Project state snapshot with schema version and task records
task.py — Core task, project, and execution models
  Project (class) — 10-15 — Project metadata with ID, title, description, and branch
  MilestoneSummary (class) — 18-21 — Milestone summary with number, title, and optional due date
  Task (class) — 24-34 — Task definition with ID, role, complexity, dependencies, and status
  TaskComment (class) — 37-41 — Comment on a task with author, body, and timestamp
  AttemptLogEntry (class) — 44-61 — Attempt log with tier, attempt number, and bounded reason
  VerdictSummary (class) — 64-67 — Verdict summary with passed flag, reason, and infeasible flag
  TokenUsage (class) — 70-73 — Token usage metrics for prompt, completion, and total tokens
  TaskExecutionRecord (class) — 76-90 — Execution record with verdict, attempts, model, files, and timing
verdict.py — Simplified review verdict model for verdicts
