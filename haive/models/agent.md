## Files

__init__.py — Package initialization for domain models
agent_output.py — Agent output schemas for code generation, review, and testing workflows
  FileToCreate (class) — 8-12 — Scaffold agent file creation request
  ScaffoldAgentOutput (class) — 15-19 — Scaffold agent output with files and notes
  FileEdit (class) — 24-28 — Code editor file modification request
  CodeEditorOutput (class) — 31-35 — Code editor output with file edits and notes
  ReviewFinding (class) — 40-47 — Individual code review finding with severity and suggestion
  ReviewAgentOutput (class) — 50-80 — Code review verdict with findings and validation
  TestGeneratorOutput (class) — 85-89 — Test generator output with test file edits
  DocumentationWriterOutput (class) — 94-98 — Documentation writer output with doc file edits
config.py — Runtime settings, environment configuration, and agent configuration models
  Settings (class) — 27-114 — Global configuration for tiers, providers, adapters, and feature flags
  AgentConfig (class) — 128-139 — Per-agent configuration with role, skills, and prompts
enums.py — Task lifecycle, agent role, and complexity enumerations
  TaskStatus (constant) — 4-11 — Enum of task states from pending to skipped
  AgentRole (constant) — 14-25 — Enum of specialized agent roles in the orchestration system
  Complexity (constant) — 28-31 — Enum of task complexity levels
discovery.py — Code section discovery and loading result models
  DiscoveredSection (class) — 8-14 — Code section metadata for discovery results
  DiscoveryResult (class) — 17-19 — Container for discovered sections with status
  LoadedSection (class) — 22-25 — Loaded source code slice with discovery reason
task.py — Task, project, and execution tracking domain models
  Project (class) — 10-15 — Project metadata and branch information
  Task (class) — 24-34 — Task definition with dependencies and acceptance criteria
  TaskComment (class) — 37-41 — Task comment metadata with author and timestamp
  AttemptLogEntry (class) — 44-61 — Execution attempt log entry with tier and reason truncation
  VerdictSummary (class) — 64-67 — Stored review verdict without suggestions
  TaskExecutionRecord (class) — 76-90 — Complete execution history for a task including attempts and token usage
orchestrator.py — Orchestrator input and output for task generation and coordination
  OrchestratorTaskView (class) — 9-22 — Task view provided to orchestrator with status and verdict
  OrchestratorInput (class) — 25-32 — Orchestrator input with project, tasks, comments, and repo map
  NewTask (class) — 35-45 — New task definition from orchestrator with acceptance criteria
  OrchestratorOutput (class) — 48-58 — Orchestrator output with new tasks and done flag
review.py — Code review verdict model with validation
  ReviewVerdict (class) — 8-31 — Review verdict with pass/fail, reason, suggestions, and uncertain flag
state.py — Project state schema with version validation
  ProjectState (class) — 10-28 — Serializable project state snapshot with schema version guard
verdict.py — Legacy review verdict model (deprecated in favor of review.py)
  ReviewVerdict (class) — 4-8 — Simplified review verdict structure
