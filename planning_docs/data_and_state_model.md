# Haive — Data and State Model

## Purpose

Defines the Pydantic schemas for every object that flows through the system: tasks, verdicts, context packs, orchestrator inputs and outputs, GitHub objects, agent outputs, and configuration. These schemas are the source of truth for inter-component contracts. If a field is not in the schema, it does not cross that boundary.

All schemas use **Pydantic v2**. Enums use `str` as the base type so they serialize cleanly to JSON.

---

## Schema Organization

```
haive/
  models/
    enums.py          — TaskStatus, AgentRole, Complexity
    task.py           — Task, Project, TaskComment, AttemptLogEntry, VerdictSummary, TokenUsage, TaskExecutionRecord
    verdict.py        — ReviewVerdict (full, Task Executor only)
    context.py        — ContextPack, RelevantSymbol, RelevantFile, BrokenReference
    orchestrator.py   — OrchestratorInput, OrchestratorTaskView, OrchestratorOutput, NewTask
    agent_output.py   — per-agent output schemas
    state.py          — ProjectState (local eval/audit store; keyed by project_id)
    config.py         — Settings (pydantic-settings)
  adapters/
    pm/
      base.py         — PMAdapter protocol
      github.py       — GitHubPMAdapter
    vcs/
      base.py         — VCSAdapter protocol
      github.py       — GitHubVCSAdapter
```

---

## Enums

```python
# models/enums.py

from enum import Enum

class TaskStatus(str, Enum):
    PENDING             = "pending"
    IN_PROGRESS         = "in_progress"
    COMPLETE            = "complete"
    NEEDS_HUMAN_REVIEW  = "needs-human-review"
    BLOCKED             = "blocked"     # downstream of a needs-human-review Issue
    SKIPPED             = "skipped"

# Note: TaskStatus maps directly to the GitHub Project "status" field values.
# "failed" is not a status — tasks either complete or need human review.

class AgentRole(str, Enum):
    SCAFFOLD_AGENT              = "scaffold_agent"
    IMPLEMENTATION_AGENT        = "implementation_agent"
    CODE_EDITOR_AGENT           = "code_editor_agent"
    REFACTORING_AGENT           = "refactoring_agent"
    API_INTEGRATION_AGENT       = "api_integration_agent"
    DATABASE_AGENT              = "database_agent"
    TEST_GENERATOR_AGENT        = "test_generator_agent"
    CODE_REVIEWER_AGENT         = "code_reviewer_agent"
    SECURITY_REVIEWER_AGENT     = "security_reviewer_agent"
    DOCUMENTATION_WRITER_AGENT  = "documentation_writer_agent"

class Complexity(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
```

---

## Domain Object Schemas

These are PM-tool-agnostic domain objects. The PM Adapter is responsible for mapping its native data model (GitHub Issues, Linear issues, Jira tickets) into these types. No other component imports adapter-specific types.

### `Project` — returned by `PMAdapter.get_project()`

```python
# models/task.py

class Project(BaseModel):
    project_id:     str       # PM tool's native ID
    title:          str
    description:    str
    project_branch: str       # VCS branch name for this project (e.g. "haive/project-7")
```

### `Task` — returned by `PMAdapter.get_tasks()`

The full domain object for a unit of work. Read from the PM tool on each run. The orchestrator, scheduler, and executor all work with this type.

```python
class Task(BaseModel):
    task_id:             str              # PM tool's native task ID
    title:               str
    description:         str
    agent_role:          AgentRole
    complexity:          Complexity
    depends_on:          list[str]        # task_ids this task depends on
    acceptance_criteria: list[str]
    status:              TaskStatus
    recovery_for:        str | None = None   # task_id of the task this recovers
    lineage_depth:       int = 0
```

### `TaskComment` — returned by `PMAdapter.read_new_comments()`

```python
class TaskComment(BaseModel):
    task_id:    str
    author:     str
    body:       str
    created_at: datetime
```

### `AttemptLogEntry` — written by the executor per attempt

One entry per attempt across all tiers. Accumulated and written to the state file on task completion or failure.

```python
class AttemptLogEntry(BaseModel):
    tier:    Complexity
    attempt: int    # attempt number within the tier (resets to 1 on tier escalation)
    reason:  str    # reviewer's reason for this attempt — never suggestions
```

### `VerdictSummary` — written to state file, read by orchestrator

The minimal verdict visible to the orchestrator. Never includes `suggestions`.

```python
class VerdictSummary(BaseModel):
    passed: bool
    reason: str
```

### `TokenUsage`

```python
class TokenUsage(BaseModel):
    prompt_tokens:     int
    completion_tokens: int
    total_tokens:      int
```

### `TaskExecutionRecord` — execution record, written by the executor to local state

The local execution record for a single task. Keyed by `task_id` in `ProjectState`. This is what the CLI reads to populate `OrchestratorTaskView.verdict` and `attempt_log` on each run.

```python
class TaskExecutionRecord(BaseModel):
    task_id:        str
    verdict:        VerdictSummary | None = None
    attempt_log:    list[AttemptLogEntry] = Field(default_factory=list)
    model_used:     str | None = None
    tier_used:      Complexity | None = None
    total_attempts: int = 0
    prompt_version: str | None = None
    changed_files:  list[str] = Field(default_factory=list)
    pr_id:          str | None = None
    completed_at:   datetime | None = None
    token_usage:    TokenUsage | None = None
    executor_start: datetime | None = None
    executor_end:   datetime | None = None
```

Serializes naturally:

```json
{
  "task_id": "103",
  "verdict": { "passed": false, "reason": "Breaks test_valid_registration on line 88." },
  "attempt_log": [
    { "tier": "medium", "attempt": 1, "reason": "Email validation missing." },
    { "tier": "high",   "attempt": 1, "reason": "Breaks test_valid_registration on line 88." }
  ],
  "tier_used": "high",
  "total_attempts": 2,
  "pr_id": null
}
```

---

## Review Verdict

The full verdict from the Review Agent. Stays within the Task Executor's retry loop — never written to the state file, never seen by the orchestrator.

```python
# models/verdict.py

class ReviewVerdict(BaseModel):
    passed:      bool
    reason:      str          # written to state file as VerdictSummary.reason
    suggestions: list[str]    # injected as feedback into next retry; never persisted
    uncertain:   bool = False # True → executor advances to next model in REVIEWER_MODELS and re-reviews
```

The executor extracts `{ passed, reason }` from this object to construct a `VerdictSummary` for the state file. `suggestions` is discarded after building the retry feedback context.

**`uncertain` escalation path:** When `uncertain=True`, the executor advances to the next model in the ordered `REVIEWER_MODELS` list and calls the Review Agent again with the same output. If all reviewer models return `uncertain`, the verdict defaults to `passed=False` and the executor proceeds with its normal retry/escalation loop. `uncertain` does not consume an executor retry — it only advances the reviewer model. `uncertain` and `passed=True` are mutually exclusive (a reviewer cannot simultaneously pass and be uncertain).

---

## Context Pack Schemas

Returned by `RepoMapService.get_context_pack()`. Consumed by the Context Assembler and (for `broken_references`) forwarded to the Review Agent.

```python
# models/context.py

class RelevantSymbol(BaseModel):
    qualified_name: str       # e.g., "UserRegistrationHandler.post"
    file:           str       # relative path from repo root
    start_line:     int
    end_line:       int
    source:         str       # AST-extracted source text

class RelevantFile(BaseModel):
    path:            str
    included_reason: str      # brief note on why this file was ranked relevant

class BrokenReference(BaseModel):
    file:   str
    symbol: str               # the symbol name that was referenced
    line:   int
    note:   str               # e.g., "referenced but definition not found"

class ContextPack(BaseModel):
    relevant_symbols:  list[RelevantSymbol]
    relevant_files:    list[RelevantFile]
    broken_references: list[BrokenReference]
    impacted_files:    list[str]             # paths only — no content
    token_estimate:    int                   # estimated token count of this pack
```

---

## Adapter Schemas

These types live in the adapter layer — no other module imports them. Each adapter translates its native data model into the domain objects above (`Task`, `Project`, `TaskComment`).

### `GitHubPMAdapter` internal types

```python
# adapters/pm/github.py (internal — not imported elsewhere)

class GitHubIssue(BaseModel):
    issue_number:        int
    title:               str
    body:                str       # human-readable description only — no embedded metadata
    gh_status:           str       # raw GitHub Project status field value
    blocked_by:          list[int] # native GH "blocked by" issue numbers
    milestone_id:        int
    # haive custom fields (from GitHub Projects v2 GraphQL API):
    haive_agent_role:          str        # raw single-select value
    haive_complexity:          str        # raw single-select value
    haive_lineage_depth:       int
    haive_recovery_for:        str | None # task_id of the task being recovered
    haive_acceptance_criteria: str        # newline-separated text

class GitHubMilestone(BaseModel):
    milestone_id:   int
    title:          str
    description:    str
    state:          str   # "open" | "closed"
    project_branch: str   # e.g. "haive/project-7"
```

`GitHubPMAdapter.get_tasks()` reads the five `haive_*` custom fields via the GitHub Projects GraphQL API and maps them to the domain `Task` fields. On startup, `GitHubPMAdapter` queries the Project's field schema and exits with a clear error listing any of the five required fields that are not present.

Custom field names on the GitHub Project:

| Custom field | Type |
|---|---|
| `haive_agent_role` | Single select — one option per `AgentRole` enum value |
| `haive_complexity` | Single select — `low`, `medium`, `high` |
| `haive_lineage_depth` | Number |
| `haive_recovery_for` | Text |
| `haive_acceptance_criteria` | Text (newline-separated list) |

---

## Orchestrator Schemas

### `OrchestratorTaskView` — per-task view passed to the orchestrator

A read-optimized projection of a `Task` merged with local state metadata. Context-budget-aware compression applied: complete tasks older than the current wave have their `attempt_log` dropped; very old complete tasks may be omitted entirely. The full record always remains in local state.

```python
# models/orchestrator.py

class OrchestratorTaskView(BaseModel):
    task_id:       str
    title:         str
    description:   str
    agent_role:    AgentRole
    complexity:    Complexity
    depends_on:    list[str]           # task_ids
    lineage_depth: int
    recovery_for:  str | None
    status:        TaskStatus
    verdict:       VerdictSummary | None       # from local state
    attempt_log:   list[AttemptLogEntry]       # from local state; dropped when not needed
```

### `OrchestratorInput` — full input to the orchestrator on each run

```python
class OrchestratorInput(BaseModel):
    project:      Project
    tasks:        list[OrchestratorTaskView]
    new_comments: list[TaskComment]     # new comments since last_run_at
    agent_summary: str                  # compact one-liner per agent, from registry
```

### `OrchestratorOutput` — what the orchestrator produces each run

```python
class NewTask(BaseModel):
    title:               str
    description:         str
    agent_role:          AgentRole
    complexity:          Complexity
    depends_on:          list[str] = Field(default_factory=list)   # task_ids
    acceptance_criteria: list[str]
    recovery_for:        str | None = None
    lineage_depth:       int = 0

class OrchestratorOutput(BaseModel):
    new_tasks: list[NewTask] = Field(default_factory=list)
    done:      bool = False    # True signals all work complete; CLI creates project → main PR
```

When `done=True`, `new_tasks` must be empty. When `done=False` and `new_tasks` is empty, this is treated as a configuration error — the orchestrator must always produce some output.

Escalation is not an orchestrator output — it happens automatically when the executor exhausts retries (PM Adapter updates status and posts comment). The orchestrator simply sees the task in `needs-human-review` status on the next run and decides whether to create a recovery task.

---

## Agent Output Schemas

Each agent role has a specific output schema. The Output Validator checks the raw LLM response against the schema for that role. All schemas are Pydantic models; the JSON schema is generated from them and stored alongside the prompts in `schemas/`.

### Common fields

All agent outputs include a `summary` field — one sentence describing what was done. This is the human-readable record of the agent's action, used in logs and PR comments.

### `ScaffoldAgentOutput`

```python
class FileToCreate(BaseModel):
    path:    str
    content: str    # full file content

class ScaffoldAgentOutput(BaseModel):
    summary:          str
    files_to_create:  list[FileToCreate]
```

### `CodeEditorOutput` and `ImplementationAgentOutput`

Agents that modify existing code produce a list of targeted edits — each edit identifies the exact string to replace and its replacement. This is precise, minimal, and verifiable.

```python
class FileEdit(BaseModel):
    path:       str
    old_string: str    # exact string to match in the file
    new_string: str    # replacement

class CodeEditorOutput(BaseModel):
    summary:      str
    edits:        list[FileEdit]
    changed_files: list[str]    # paths the agent claims to have modified
                                # verified against git diff after application
```

`ImplementationAgentOutput` uses the same schema as `CodeEditorOutput`.

### `RefactoringAgentOutput`

Same schema as `CodeEditorOutput`. The Review Agent additionally checks that `changed_files` does not include any path not listed in the task's context — enforcing the hard file-scope constraint.

### `ReviewAgentOutput` (internal — maps to `ReviewVerdict`)

```python
class ReviewAgentOutput(BaseModel):
    passed:      bool
    reason:      str
    suggestions: list[str]
```

This is the same as `ReviewVerdict`. Defined separately to make the schema registration explicit.

### Remaining agent output schemas

`ApiIntegrationAgentOutput`, `DatabaseAgentOutput`, `TestGeneratorOutput`, `CodeReviewerOutput`, `SecurityReviewerOutput`, `DocumentationWriterOutput` all follow `CodeEditorOutput` for file-modifying agents, or a findings-list pattern for review agents. Exact field definitions are deferred to implementation — the structural pattern is established above.

---

## State File Schema

The state file is haive's internal audit log and eval dataset. **It is not the source of truth for task status or dependencies** — the PM tool is. The state file holds execution metadata that belongs to haive's observability layer.

Each project gets its own file at `~/.haive/state/{owner}/{repo}/project_{id}.json`. State files live outside the project directory so they persist across sessions and are never accidentally committed.

```python
# models/state.py

class TaskExecutionRecord(BaseModel):
    task_id:        str               # PM tool's native task ID
    verdict:        VerdictSummary | None = None
    attempt_log:    list[AttemptLogEntry] = Field(default_factory=list)
    model_used:     str | None = None
    tier_used:      Complexity | None = None
    total_attempts: int = 0
    prompt_version: str | None = None
    changed_files:  list[str] = Field(default_factory=list)
    pr_id:          str | None = None     # VCS PR identifier (None if retries exhausted)
    completed_at:   datetime | None = None
    token_usage:    TokenUsage | None = None
    executor_start: datetime | None = None
    executor_end:   datetime | None = None

class ProjectState(BaseModel):
    schema_version: str = "1"             # bump when schema changes; triggers clear error on mismatch
    project_id:     str                   # PM tool's native project ID
    tasks:          dict[str, TaskExecutionRecord]  # keyed by task_id
    created_at:     datetime
    updated_at:     datetime
    last_run_at:    datetime | None = None   # used as `since` for read_new_comments
```

The `tasks` dict is append-only — records are added when an executor completes, never removed. Concurrent executor writes are serialized via a file lock: read → merge → write full file. File lock is held only during the write, not during execution.

**What is NOT in the state file:** task status, dependency relationships, task titles or descriptions. These all live in the PM tool.

---

## Agent Registry Schema

The YAML registry is validated against this schema at startup. A validation failure (missing required field, unknown agent role) causes haive to exit with an error rather than run with an invalid configuration.

```python
# models/config.py (partial)

class AgentConfig(BaseModel):
    description:               str
    skills:                    list[str]
    system_prompt:             str          # relative path: prompts/agent_name.md
    prompt_version:            str          # semver: "1.0.0"
    max_tokens:                int
    output_schema:             str          # relative path: schemas/agent_name_result.json
    retry_limit:               int
    context_budget_multiplier: float = 1.0  # future option; 1.0 = no adjustment
```

---

## Configuration Schema

All runtime configuration loaded from `.env` via `pydantic-settings`. List fields (model lists) use comma-separated values in `.env`.

```python
# models/config.py

from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Orchestrator
    orchestrator_model: str

    # Tier config
    tier_low_models:           list[str]
    tier_low_max_attempts:     int = 2
    tier_low_context_budget:   int = 8000

    tier_medium_models:        list[str]
    tier_medium_max_attempts:  int = 2
    tier_medium_context_budget: int = 16000

    tier_high_models:          list[str]
    tier_high_max_attempts:    int = 2
    tier_high_context_budget:  int = 32000

    reviewer_models:           list[str]

    # Recovery
    max_recovery_depth: int = 3

    # Concurrency
    max_executors: int = 4

    # Providers
    anthropic_api_key: str | None = None
    openai_api_key:    str | None = None
    ollama_api_base:   str = "http://localhost:11434"

    # Adapter selection
    pm_adapter:  str = "github"   # "github" | "linear" | "jira"
    vcs_adapter: str = "github"   # "github" | "gitlab"

    # GitHub adapter (required when pm_adapter="github" or vcs_adapter="github")
    github_token:      str | None = None
    github_repo:       str | None = None   # "owner/repo"
    github_project_id: int | None = None   # GitHub Projects number (pm_adapter="github" only)

    model_config = SettingsConfigDict(
        env_file=ConfigManager.active_config_path(),  # resolves to ~/.haive/configs/<active>.env
        env_list_separator=","
    )
```

---

## Schema Constraints Enforced at Boundaries

These constraints are structural — enforced by field omission, not by validation rules. If a field does not exist on a schema, it cannot be passed.

| Boundary | What is excluded by schema design |
|---|---|
| `OrchestratorTaskView` | No `suggestions`, no full agent output, no code content, no token counts |
| `VerdictSummary` (local state + orchestrator) | No `suggestions` — only `passed` and `reason` |
| `ContextPack` | No full file contents — symbols and snippets only |
| `OrchestratorInput` | No changed file lists, no token counts, no model names |
| `NewTask` (orchestrator output) | No model names, no file paths, no implementation hints |
| `AttemptLogEntry` | No `suggestions` — only the `reason` from each attempt |
| `Task` (domain object from PM adapter) | No attempt_log, no token_usage — those live in local state only |
| `ProjectState` | No task descriptions, no acceptance criteria — those live in the PM tool |

The "What Is Never Passed" table in the Communication Protocol doc describes the intent; these schema definitions are the enforcement mechanism.
