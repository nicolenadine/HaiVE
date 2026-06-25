# Haive — Architecture Overview

## Purpose

Haive is a multi-provider AI agent harness for coordinating software development work. A human creates a project in their PM tool of choice (GitHub Issues, Linear, Jira) and points haive at it; the orchestrator reads the project description, creates tasks in the PM tool, and routes each task to a disposable task executor. Executors run on the model tier appropriate for each task's complexity, with automatic retry and model escalation. When a task passes internal review, the executor submits a PR targeting the project branch and auto-merges it — no human input required. When a task exhausts all retries, the executor flags it `needs-human-review`, leaves a comment summarizing every attempt and all reviewer feedback, and haive continues with independent tasks. The human adds context as a task comment and re-runs haive. When all tasks complete, haive opens a PR from the project branch to main for final human review. All decisions and outputs are observable via OpenTelemetry.

## Non-Goals (for the initial version)

- Fully autonomous development without human oversight
- Multi-user collaboration or shared state
- Production-grade distributed execution
- Advanced UI or full IDE integration
- Complex permissions or access control

---

## Core Design Principle: Coordinator and Disposable Workers

The system has two distinct agent lifecycles:

**Orchestrator — long-lived coordinator.** One instance per milestone. Maintains project progress state across sessions. Sees only task verdicts, never full agent outputs. Its context grows slowly and predictably.

**Task Executors — stateless disposable workers.** One per task. Spun up with exactly the context needed for that task. Return a verdict. Shut down. No shared state between workers. Tasks with no dependencies can run in parallel as independent workers.

The PM tool is the coordination layer between them. The orchestrator creates tasks in the PM tool and sets dependency relationships; the Task Scheduler reads tasks to determine what to run; executors submit PRs and update task status when done. No direct communication between orchestrator and executor. The local state file holds internal execution metadata (attempt logs, token usage, timing) that belongs to haive's observability layer — not to the coordination protocol.

Haive accesses the PM tool and the VCS host through separate pluggable adapter interfaces. The v1 implementation uses GitHub for both. Swapping to Linear + GitHub, or Jira + GitLab, requires only a new adapter implementation — no changes to the orchestrator, scheduler, or executor.

---

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Harness CLI                              │
│      (entry point — accepts --project <id>, drives run)         │
└──────────────────┬──────────────────────────┬───────────────────┘
                   │                          │
                   ▼                          ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│         PM Adapter           │  │        VCS Adapter           │
│  (interface — pluggable)     │  │  (interface — pluggable)     │
│                              │  │                              │
│  get_project(project_id)     │  │  create_branch(name, base)   │
│  get_tasks(project_id)       │  │  push_commits(branch, ...)   │
│  create_task(...)            │  │  create_pr(title, ...)       │
│  update_status(task_id, ...) │  │  merge_pr(pr_id)             │
│  set_dependency(task_id, ...)│  │  add_pr_comment(pr_id, ...) │
│  add_comment(task_id, body)  │  │  create_project_pr(...)      │
│  read_new_comments(since)    │  │                              │
│                              │  │  v1: GitHubVCSAdapter        │
│  v1: GitHubPMAdapter         │  └──────────────────────────────┘
└──────────────────┬───────────┘
                   │ creates / reads tasks
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Orchestrator                              │
│  (long-lived — reads Project + Task statuses + comments via     │
│   PM Adapter, creates Tasks, reads verdicts, decides next step. │
│   Never sees full agent output or code file contents.)          │
└────────────────┬────────────────────────────────────────────────┘
                 │ creates Tasks → PM Adapter → [PM tool]
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Task Scheduler                             │
│  (deterministic — reads Tasks via PM Adapter, evaluates DAG,    │
│   manages executor pool, caps concurrency at MAX_EXECUTORS)     │
│  No RepoMapService involvement — pure sequencing only.          │
└────────────────┬────────────────────────────────────────────────┘
                 │ spawns (up to MAX_EXECUTORS in parallel)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Task Executor                               │
│  (disposable — owns the full lifecycle of one task)             │
│                                                                 │
│  START: VCS Adapter: create task branch                         │
│         PM Adapter:  update task status → in_progress           │
│         RepoMapService.get_context_pack(task, token_budget)     │
│                                                                 │
│  ┌──────────────────┐  ┌───────────────┐                        │
│  │ Context Assembler│→ │   LiteLLM     │                        │
│  │ (formats context │  │ (sub-agent    │                        │
│  │  pack into prompt│  │  call)        │                        │
│  │  no service calls│  │               │                        │
│  └──────────────────┘  └───────┬───────┘                        │
│                                │                                │
│                      ┌─────────▼───────┐                        │
│                      │Output Validator │                        │
│                      │(schema, deterministic)                   │
│                      └─────────┬───────┘                        │
│                                │                                │
│                      ┌─────────▼───────┐                        │
│                      │ Review Agent    │                        │
│                      │(LLM-as-judge,   │                        │
│                      │ receives broken │                        │
│                      │ refs as context)│                        │
│                      └─────────┬───────┘                        │
│                                │                                │
│               retry/escalate loop                               │
│                                                                 │
│  ON PASS:                                                       │
│    VCS Adapter: commit → create PR → merge                      │
│    PM Adapter:  update task status → complete                   │
│    RepoMapService.update_files(changed_files)                   │
│                                                                 │
│  ON RETRIES EXHAUSTED:                                          │
│    PM Adapter: add_comment (full attempt summary)               │
│    PM Adapter: update task status → needs-human-review          │
└─────────────────────────────────────────────────────────────────┘
                 │ (OTel spans emitted throughout)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│           Observability (OTel + OpenInference + Phoenix)        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Local State File (eval + audit log)                │
│    (keyed by project_id. Not the coordination bus.)             │
│                                                                 │
│  attempt_log per task — tier, attempt, reviewer reason          │
│  token_usage per task — prompt/completion/total                 │
│  last_run_at           — used for comment polling since         │
│  timing data           — executor start/end, duration           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     RepoMapService                              │
│    (called only by Task Executor. DuckDB-backed. Deterministic.)│
│                                                                 │
│  scan_repo()                    — full build at startup         │
│  get_context_pack(task, budget) — called at task start          │
│    returns: relevant symbols, file snippets, broken references, │
│             impacted files — all within token budget            │
│  update_files(paths)            — called at task end            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Descriptions

### 1. Harness CLI

User-facing entry point. Accepts a GitHub Milestone ID or number via `--milestone <id>`. Initializes the observability layer (registers OTel instrumentors, configures Phoenix OTLP exporter). Drives the orchestration loop. Streams task status to the terminal. Exits after each wave of task PRs is submitted; re-invoked by the human to continue after addressing any `needs-human-review` Issues.

Technology: Typer. Config loaded via pydantic-settings from the active named config (`~/.haive/configs/<active>.env`). Named configs are created and switched with `haive config` subcommands — no flags required on `haive run`.

### 2. PM Adapter

The PM Adapter is an interface that abstracts all task management operations. No other component calls PM tool APIs directly. The v1 implementation is `GitHubPMAdapter`; future implementations cover Linear, Jira, and others.

**Interface:**
```python
class PMAdapter(Protocol):
    def get_project(self, project_id: str) -> Project
    def get_tasks(self, project_id: str) -> list[Task]
    def create_task(self, project_id: str, task: NewTask) -> str          # returns task_id
    def set_dependency(self, task_id: str, depends_on: list[str]) -> None
    def update_status(self, task_id: str, status: TaskStatus) -> None
    def add_comment(self, task_id: str, body: str) -> None
    def read_new_comments(self, project_id: str, since: datetime) -> list[TaskComment]
```

**What it reads:** project description, all tasks with their current status and dependency relationships, new comments since `last_run_at` (for human guidance after a `needs-human-review` flag).

**What it writes (orchestrator-driven):** new tasks with title, description, role, complexity, acceptance criteria; dependency relationships; task status updates.

**What it writes (executor-driven):** task status transitions (`in_progress` → `complete` or `needs-human-review`); attempt summary comments when retries are exhausted.

**`GitHubPMAdapter` notes:** Uses GitHub Issues for tasks. All haive-specific task metadata is stored as **GitHub Projects v2 custom fields** — not embedded in the Issue body. Status is tracked via the built-in Project `status` field. Dependency relationships use GitHub's native "blocked by" feature.

Required custom fields (pre-configured on the GitHub Project before haive can use it):

| Field name | Type | Values |
|---|---|---|
| `haive_agent_role` | Single select | one per `AgentRole` enum value |
| `haive_complexity` | Single select | `low`, `medium`, `high` |
| `haive_lineage_depth` | Number | integer |
| `haive_recovery_for` | Text | `task_id` of the task being recovered, or empty |
| `haive_acceptance_criteria` | Text | newline-separated list |

`GitHubPMAdapter` verifies all five fields exist on startup and exits with a clear error listing any missing fields. All reads and writes use the GitHub Projects GraphQL API (already required for `status`). The Issue body is left as a human-readable description only.

Config variables specific to `GitHubPMAdapter` (set via `haive config set`):
- `GITHUB_TOKEN` — personal access token with repo, Issues, and Projects read/write permissions
- `GITHUB_REPO` — target repository in `owner/repo` format
- `GITHUB_PROJECT_ID` — the GitHub Project (v2) number

### 3. VCS Adapter

The VCS Adapter is an interface that abstracts all version control operations. The v1 implementation is `GitHubVCSAdapter`; future implementations cover GitLab, Gitea, and others.

**Interface:**
```python
class VCSAdapter(Protocol):
    def create_branch(self, name: str, base: str) -> None
    def push_commits(self, branch: str, changed_files: list[str], message: str) -> None
    def create_pr(self, title: str, body: str, head: str, base: str) -> str  # returns pr_id
    def merge_pr(self, pr_id: str) -> None
    def add_pr_comment(self, pr_id: str, body: str) -> None
    def create_project_pr(self, head: str, base: str, title: str, body: str) -> str
```

**What it does:** creates per-task branches off the project branch, pushes committed changes, opens task PRs targeting the project branch, auto-merges them when review passes, adds assumption comments to PRs, and creates the final project-branch → main PR when `done=True`.

**What it does NOT do:** delete branches or PRs. Haive never destroys the record of its own work.

**`GitHubVCSAdapter` notes:** `push_commits` runs `git add <files> && git commit -m "<message>" && git push origin <branch>` via subprocess — not the GitHub content API. This produces a single atomic commit per task (all changed files together), is simpler to implement, and requires no per-file SHA lookups. Requires `git` on the system `PATH` — verified at startup alongside other preflight checks. `create_branch` and PR operations use PyGithub. Auto-merge requires the repository to have auto-merge enabled in settings and the token to have merge permissions.

### 4. Orchestrator

The orchestrator answers one question per loop iteration: *given what has been completed and what has failed, what is the next task or are we done?*

It is a thin coordinator, not a reasoning engine for code quality.

**What it receives at startup:**
- The Milestone object from GitHub Service: title, description — this is the objective
- A compact agent summary derived from the registry — loaded once, not re-sent each loop

**What it receives per loop:**
- All tasks in the project with their current status from the PM tool: pending, in_progress, complete, needs-human-review
- For complete tasks: the `VerdictSummary` read from local state — `{ passed: true, reason: str }`
- For needs-human-review tasks: `{ passed: false, reason: str }` and the full `attempt_log` from local state
- New task comments since `last_run_at` — the human may have left guidance on a `needs-human-review` task

**What it produces:**
- New tasks to create, each with:
  - `title: str`
  - `description: str`
  - `agent_role: AgentRole`
  - `complexity: low | medium | high`
  - `depends_on: list[task_id]` — passed to `PMAdapter.set_dependency`
  - `acceptance_criteria: list[str]`
  - `recovery_for: task_id | null` — set when this is a recovery attempt for a prior failure
  - `lineage_depth: int` — 0 for original tasks, increments with each recovery generation
- Or a completion signal (`done=True` → CLI calls `VCSAdapter.create_project_pr(project_branch → main)`)

**Recovery before escalation.** When the orchestrator reads a `needs-human-review` task with human comments, it can create a recovery task incorporating that guidance. It only leaves a `needs-human-review` status in place (rather than creating another recovery attempt) when it judges the human's context is insufficient to proceed, or when `lineage_depth` exceeds `MAX_RECOVERY_DEPTH`. Independent tasks continue running throughout — haive never blocks the whole run on a single failure.

**Complexity** is a single field representing `max(coding_difficulty, security_sensitivity)`. The orchestrator makes one judgment — low, medium, or high — which drives model tier selection.

**What the orchestrator never sees:** file contents, agent outputs, review prose, code diffs, model names. Only verdicts, task statuses, and task comment threads.

**Model:** A capable model (Claude Sonnet or equivalent) configured via `ORCHESTRATOR_MODEL` in `.env`. The orchestrator is the one component where model quality matters most — it maintains project coherence over the full run.

```env
MAX_RECOVERY_DEPTH=3   # orchestrator gets 3 recovery generations before leaving issue in needs-human-review
```

### 5. State File

A JSON file that is haive's internal audit log and eval dataset. **Not the coordination bus** — the PM tool is authoritative for task status and scheduling decisions. The state file holds data that belongs to haive's observability layer, not to the PM tool's visible record.

**Scoped per project.** Each project gets its own state file at `~/.haive/state/{owner}/{repo}/project_{id}.json`. State files live outside the project directory — they persist across sessions and are not accidentally committed.

Contents:
- Project ID (reference back to PM tool)
- `last_run_at` — used as the `since` argument to `read_new_comments` on each run
- Per-task execution records, keyed by `task_id` (PM tool's native task ID):
  - `attempt_log` — one entry per attempt across all tiers: tier name, attempt number, reviewer reason
  - `token_usage` — prompt/completion/total per task
  - Timing: executor start/end, total duration
  - `model_used`, `tier_used`, `total_attempts`, `prompt_version`
  - `changed_files` — from `git diff --name-only` after the task runs

Not a database. No queries. Human-readable audit trail and eval dataset for scoring prompt and model changes over time.

### 6. Task Scheduler

A deterministic component — no LLM. Reads tasks via the PM Adapter and manages the executor pool.

**Dependency resolution.** For each task in the project, the scheduler computes its current readiness from the task list returned by `PMAdapter.get_tasks()`:

| Status | Condition |
|---|---|
| `ready` | status is `pending` AND all `depends_on` tasks have status `complete` |
| `waiting` | status is `pending` AND at least one `depends_on` task is still `in_progress` |
| `blocked` | status is `pending` AND at least one `depends_on` task has status `needs-human-review` |

This is a DAG traversal — topological sort over the dependency graph. Fully deterministic. The PM tool's native dependency representation (GitHub "blocked by", Linear "blocking", Jira "is blocked by") is abstracted away by the adapter — the scheduler works only with `Task.depends_on: list[str]`.

**Executor pool.** The scheduler maintains a pool of running executors. When a slot is free (a running executor completes) and a ready task exists, it spawns a new executor. Concurrency is capped at `MAX_EXECUTORS` from `.env`.

Implementation: Python `asyncio` with an `asyncio.Semaphore`. Task executors are I/O-bound (waiting on LLM API responses), so async concurrency is appropriate without threads.

**On dependency failure.** When a task transitions to `needs-human-review`, its downstream tasks move to `blocked` status and continue waiting. The scheduler continues running independent tasks. The run makes as much forward progress as possible rather than halting entirely.

**The Task Scheduler has no awareness of code files or the RepoMapService.** That is entirely the Task Executor's responsibility. The Scheduler's only concern is: which tasks are ready, how many are running, and what to spawn next.

**Config:**
```env
MAX_EXECUTORS=4
```

### 7. Agent Registry

A YAML file mapping each `AgentRole` to its configuration. Agent definitions contain no model references — model selection is entirely driven by task complexity at runtime.

Each agent entry includes a `description` and a `skills` list. These exist specifically to inform the orchestrator's routing decisions — they are the only fields the orchestrator ever reads from the registry.

```yaml
roles:
  code_generator:
    description: Writes new code from a specification.
    skills: [implementation, feature scaffolding, boilerplate, API integration]
    system_prompt: prompts/code_generator.md
    max_tokens: 4096
    output_schema: schemas/code_generation_result.json
    retry_limit: 2

  test_generator:
    description: Writes tests for existing code.
    skills: [unit tests, integration tests, test fixtures, coverage gaps]
    system_prompt: prompts/test_generator.md
    max_tokens: 4096
    output_schema: schemas/test_generation_result.json
    retry_limit: 2

  code_reviewer:
    description: Reviews code for correctness and quality.
    skills: [bug detection, style, security patterns, guideline compliance]
    system_prompt: prompts/code_reviewer.md
    max_tokens: 2048
    output_schema: schemas/code_review_result.json
    retry_limit: 1
```

**What the orchestrator sees.** At startup, the registry is read and a compact summary is derived — one line per agent, ~30–50 tokens each. This summary is loaded into the orchestrator's context once. The orchestrator uses it to select `agent_role` for each task. It never sees system prompts, output schemas, token limits, or retry budgets.

```
code_generator: Writes new code from a specification. Skills: implementation, feature scaffolding, boilerplate, API integration.
test_generator: Writes tests for existing code. Skills: unit tests, integration tests, test fixtures, coverage gaps.
code_reviewer: Reviews code for correctness and quality. Skills: bug detection, style, security patterns, guideline compliance.
```

**Skills overlap is an agent design concern, not a registry concern.** If two agents have heavily overlapping skills, the orchestrator will make ambiguous routing decisions. The fix is writing clear, non-overlapping agent definitions — addressed in the Agent Model doc.

**Skills lists also enable future deterministic pre-filtering.** If routing ever needs to be deterministic before the orchestrator reasons about it (e.g., keyword match on task description → candidate agent shortlist), the structured `skills` list makes that possible without changing the registry format.

### 8. Model Configuration

All model names, tier definitions, and retry budgets live in the active named config (`~/.haive/configs/<active>.env`) and are loaded by pydantic-settings at startup. Set or change them with `haive config set` — no code changes required.

```env
# Orchestrator
ORCHESTRATOR_MODEL=claude-sonnet-4-6

# Review agent — also a list for within-tier fallback
REVIEWER_MODELS=claude-haiku-4-5-20251001,gpt-4o-mini

# Task executor tiers — lists enable within-tier provider fallback via LiteLLM
TIER_LOW_MODELS=ollama/mistral,ollama/llama3
TIER_LOW_MAX_ATTEMPTS=2

TIER_MEDIUM_MODELS=claude-haiku-4-5-20251001,gpt-4o-mini
TIER_MEDIUM_MAX_ATTEMPTS=2

TIER_HIGH_MODELS=claude-sonnet-4-6,gpt-4o
TIER_HIGH_MAX_ATTEMPTS=2

# Scheduler
MAX_EXECUTORS=4
```

**Complexity → starting tier:**
- `low` → TIER_LOW
- `medium` → TIER_MEDIUM
- `high` → TIER_HIGH (never starts below this)

### 9. Task Executor

A disposable worker. One is created per task, with a fresh context window. When the task is done — pass or retries exhausted — the executor exits. The next task gets a new executor with no memory of previous tasks.

The executor owns the retry/escalation loop for its single task and the PR submission:

```
# Setup
VCSAdapter.create_branch(f"haive/task-{task.task_id}", base=project_branch)
PMAdapter.update_status(task.task_id, IN_PROGRESS)

current_tier = tier_for(task.complexity)
attempt = 1
feedback = None

# Retry loop
loop:
    Context Assembler → calls RepoMapService.get_context_pack(task, budget)
                     → builds prompt (task description, acceptance criteria,
                                       comment thread, code context, feedback if attempt > 1)
    response = LiteLLM.call(current_tier.models, prompt)
        # LiteLLM handles within-tier provider fallback transparently
        # if all models in tier are unavailable → treat as escalation trigger

    Output Validator → schema check (deterministic)
        # fail → retry or escalate (no reviewer call on schema failure)

    Review Agent → quality judgment
        # returns { passed: bool, reason: str, suggestions: list }
        # summary verdict written to local state for observability

    if passed:
        commit changes to task branch
        pr_id = VCSAdapter.create_pr(title, body, head=task_branch, base=project_branch)
        VCSAdapter.add_pr_comment(pr_id, body="Assumptions: ...")
        VCSAdapter.merge_pr(pr_id)
        PMAdapter.update_status(task.task_id, COMPLETE)
        write attempt_log + token_usage + pr_id to local state
        RepoMapService.update_files(changed_files)
        exit ✓

    attempt += 1
    feedback = review.suggestions

    if attempt > current_tier.max_attempts:
        if next tier exists:
            current_tier = next_tier
            attempt = 1
            # feedback carries forward into next tier
        else:
            PMAdapter.add_comment(task.task_id, body="Attempt summary: ...")
            PMAdapter.update_status(task.task_id, NEEDS_HUMAN_REVIEW)
            write attempt_log to local state
            exit  # orchestrator reads comments on next haive run
```

**Three distinct failure modes — handled separately:**

| Failure | Cause | Response |
|---|---|---|
| API / infra error | Rate limit, timeout, 500 | LiteLLM tries next model in tier list. Transparent to executor. Does not consume a retry. |
| Bad output | Schema invalid or reviewer rejects | Retry same tier with reviewer feedback appended to context. Consumes a retry. |
| Tier exhausted | Max retries on bad output | Escalate to next tier (feedback carries forward) or set `needs-human-review`. |

**Retry feedback carries forward across tier escalation.** If a medium-tier attempt produced output that was 70% correct, that context is valuable for the high-tier attempt. The prompt gets longer, but the quality signal is worth it.

**Parallelism.** Tasks with no `depends_on` relationships can run as simultaneous executors. Each has its own isolated context window and task branch. The project branch receives each merged PR in turn — independent task PRs merge in any order; dependent tasks don't start until their dependency PRs are merged into the project branch.

### 10. RepoMapService

A shared, deterministic service that maintains a live structural map of the codebase. It is the authoritative source of file and symbol information — used by the Task Executor's Context Assembler to build agent prompts.

Backed by **DuckDB** (a zero-infrastructure analytical database, better than SQLite for the graph traversal and ranking queries this service runs).

**Interface:**

```python
RepoMapService
├── scan_repo()                          # full build at startup
├── update_files(paths: list[str])       # incremental refresh after agent edits
└── get_context_pack(task, token_budget) # returns impacted_files and broken_references within the pack
```

**How it builds the map — Aider repo map approach:**

Uses `tree-sitter` to parse every file in the codebase into an AST. Extracts all defined symbols (functions, classes, methods) and all references (calls, imports). Builds a graph where nodes are files and edges represent "file A references a symbol defined in file B." Runs a PageRank-style ranking algorithm over this graph to score file relevance for any given task. No vector embeddings — purely structural and graph-based. Fully reproducible.

**Language extensibility via `LanguageParser` protocol:**

```python
class LanguageParser(Protocol):
    extensions: list[str]               # e.g. [".py"] or [".ts", ".tsx"]
    def parse_file(self, path: str, content: str) -> ParsedFile: ...
```

`scan_repo(root, parsers=[PythonParser()])` dispatches each file to the parser that owns its extension. v1 ships `PythonParser` only — a Python grammar via tree-sitter. Adding TypeScript later is a new `TypeScriptParser` class, no changes to `RepoMapService`. At startup, if no registered parser matches any file in the repo, haive warns the user rather than silently producing an empty map.

v1 scope: **Python only.** All files with non-`.py` extensions are ignored.

**`get_context_pack(task, token_budget)`** is the primary integration point with the Context Assembler. Given a task description and a token budget, it returns:
```
{
  "relevant_files": [...],
  "relevant_symbols": [...],   # with extracted source via AST
  "impacted_files": [...],     # files that reference the relevant symbols
  "broken_references": [...]   # any currently unresolved references
}
```
The token budget ensures the context pack never exceeds what the agent can receive.

**Incremental invalidation — not a full rebuild on every change:**

Uses content hashes to detect what actually changed. Only re-parses files whose hash has changed. Graph edges for changed files are removed and recomputed.

```python
if file_hash unchanged:
    skip
if file_hash changed:
    re-parse file
    remove old symbols/references for this file
    insert new symbols/references
    update graph edges
    flag dependents for broken reference check
```

**Schema versioning:** Each cache entry stores `parser_version` and `extractor_version`. If parser logic improves, old entries are invalidated even if file content hasn't changed.

**Git as source of truth:** After each Task Executor completes, the Task Scheduler uses `git diff --name-only` and `git status --porcelain` to determine which files actually changed — not self-reporting from the agent. Agents can crash or misreport; git does not.

**Three refresh levels:**

| Level | When | Scope |
|---|---|---|
| Fast | After each agent edit | Re-parse only changed files (via git diff) |
| Medium | Before each new orchestrator loop (Harness CLI) | Refresh all dirty files via `get_changed_files` + `update_files` |
| Full | On branch switch, merge, parser upgrade, cache corruption | Rebuild entire map |

**DuckDB schema:**

```sql
files(id, path, language, content_hash, last_indexed_at,
      parser_version, extractor_version, parse_status)

symbols(id, file_id, name, qualified_name, kind,
        start_line, end_line, signature)

references(id, file_id, symbol_name, line_number,
           resolved_symbol_id NULLABLE)

edges(id, from_file_id, to_file_id, symbol_name, weight)
```

The `edges` table is what the PageRank-style ranker operates over. The `references.resolved_symbol_id` being NULL indicates a broken reference — a symbol is referenced but its definition no longer exists.

### 10. Context Assembler

Builds the prompt for each agent call. Fully deterministic — no LLM call.

Primary input is the context pack returned by `RepoMapService.get_context_pack(task, token_budget)`. The Context Assembler does not do its own file discovery — that is entirely the RepoMapService's responsibility.

Assembles in order:
1. Agent system prompt (read from registry)
2. Task description and acceptance criteria
3. Relevant symbols and file snippets (from context pack — AST-extracted, not whole files)
4. Impacted files flagged by RepoMapService (for awareness, not full inclusion)
5. Outputs of `depends_on` tasks (looked up from state file)
6. Reviewer feedback from prior attempts (if attempt > 1)

What it explicitly excludes: orchestrator reasoning, outputs of unrelated tasks, full file contents when a symbol snippet suffices, prior run history.

The token budget passed to `get_context_pack` ensures the assembled prompt stays within bounds before it is built — not after. The Context Assembler is the enforcement point for token efficiency. Its output is fully reproducible from the task definition and the current repo map state.

### 11. Output Validator

Deterministic schema check after each LLM call. Parses the raw response (JSON extraction from text if needed) and validates it against the agent role's Pydantic output schema.

On schema failure: retry or escalate (same logic as the review failure path, but does not invoke the Review Agent — no point judging quality if the output isn't even parseable).

### 12. Review Agent

An LLM-as-judge that evaluates whether a sub-agent's output is actually good — not just structurally valid.

**Produces output for two audiences with different needs:**

- **Task Executor** receives the full output: `{ passed: bool, reason: str, suggestions: list[str] }`. Used to build retry context. The suggestions become the feedback appended to the next attempt's prompt.
- **Orchestrator** receives only the summary: `{ passed: bool, reason: str }`. Terse and structured. The orchestrator acts on this, never reads prose.

The Review Agent checks against the task's `acceptance_criteria` and the project's guidelines (injected from a project guidelines file). It does not generate code or suggest implementations — it judges and explains.

Model: configured via `REVIEWER_MODELS` in `.env`. Uses the same tier fallback pattern as task executors.

### 13. Observability Layer

Wired in from the start. Every component emits OTel spans. The full hierarchy — run → task → LLM call — is visible in Phoenix.

**Stack:**
- **OpenTelemetry SDK** — all custom spans (run, task executor lifecycle, review, checkpoint events) written against the OTel API. Backend-agnostic.
- **OpenInference auto-instrumentation** (`openinference-instrumentation-litellm`) — wraps LiteLLM at startup. Every LLM call emits a span with standardized attributes: model, prompt, completion, token counts, cost, latency. Zero application code required.
- **Arize Phoenix** — local OTel backend. Receives spans via OTLP. Provides trace UI and `phoenix.evals` for batch evaluation.

**Swapping backends:** Change the OTLP endpoint in `.env`. No instrumentation code changes.

**Span attributes of note:**
- Task executor spans: `task.id`, `task.role`, `task.complexity`, `attempt.number`, `tier.name`, `tier.model_used`, `verdict.passed`
- Human checkpoint events: `checkpoint.reason`, `checkpoint.attempts_made`, `checkpoint.models_tried`

**Evals:** `phoenix.evals` runs as a batch job against collected traces. Eval templates define what "good" looks like per agent role. An LLM judge scores each trace; scores attach to spans. Builds a dataset of scored runs for systematic evaluation of prompt or model changes over time.

---

## Task Lifecycle

```
Harness CLI receives --project <id>
│
├── OTel: open "haive.run" span
├── PMAdapter.get_project(project_id) → Project (title, description, project_branch)
├── PMAdapter.get_tasks(project_id)   → list[Task] (statuses + dependencies)
├── Load or initialize local state file (project_<id>.json)
├── PMAdapter.read_new_comments(project_id, since=state.last_run_at) → new comments
├── Update state.last_run_at = now(); save state
│
├── Orchestrator call (LLM)
│   Input:  Project object + Task statuses + verdicts (from local state)
│           + new comments (human guidance if any)
│           (no file content, no agent output detail)
│   Output: new Tasks to create (title, description, role, complexity,
│                                depends_on, acceptance_criteria,
│                                recovery_for, lineage_depth)
│           OR done=True → CLI creates project branch → main PR
│
├── PMAdapter.create_task(...) + PMAdapter.set_dependency(...) for each NewTask
│
├── Task Scheduler (deterministic)
│   ├── Re-reads tasks via PMAdapter.get_tasks() → evaluates DAG
│   ├── ready / waiting / blocked per Task (based on Task.depends_on + statuses)
│   ├── Spawns executor for each ready Task (up to MAX_EXECUTORS)
│   ├── On executor completion: re-evaluates graph, spawns newly-unblocked Tasks
│   └── On needs-human-review: marks downstream Tasks blocked, continues independent Tasks
│
├── For each ready Task (parallel, managed by Task Scheduler):
│   │
│   ├── Spin up Task Executor (fresh context)
│   ├── OTel: open "haive.task" span
│   │
│   ├── VCSAdapter.create_branch(f"haive/task-{task.task_id}", base=project_branch)
│   ├── PMAdapter.update_status(task.task_id, IN_PROGRESS)
│   │
│   ├── RepoMapService.get_context_pack(task, token_budget)
│   │   returns: relevant symbols, file snippets, broken references,
│   │            impacted files — all within token budget
│   │
│   ├── [retry/escalation loop]
│   │   │
│   │   ├── Context Assembler (formats context pack into prompt)
│   │   │   system prompt + task description + acceptance criteria + comment thread
│   │   │   + dependency task summaries + symbols/snippets + broken ref info
│   │   │   + reviewer feedback (if retry)
│   │   │   No service calls — receives data, formats it.
│   │   │
│   │   ├── LiteLLM call (current tier)
│   │   │   └── OTel: "haive.llm.call" span (auto-instrumented)
│   │   │       LiteLLM handles within-tier provider fallback transparently
│   │   │
│   │   ├── Output Validator (schema check, deterministic)
│   │   │   └── fail → retry/escalate without calling Review Agent
│   │   │
│   │   ├── Review Agent (LLM-as-judge)
│   │   │   receives broken ref info as context — no service calls
│   │   │   ├── pass  → break out of loop
│   │   │   └── fail  → append suggestions to feedback, retry or escalate
│   │   │
│   │   └── [if tier ladder exhausted] → go to ON RETRIES EXHAUSTED below
│   │
│   ├── ON PASS:
│   │   ├── commit changes to task branch
│   │   ├── VCSAdapter.create_pr(title, body, head=task_branch, base=project_branch)
│   │   ├── VCSAdapter.add_pr_comment(pr_id, assumptions/questions)
│   │   ├── VCSAdapter.merge_pr(pr_id)
│   │   ├── PMAdapter.update_status(task.task_id, COMPLETE)
│   │   ├── Write attempt_log + token_usage + pr_id + changed_files to local state
│   │   └── RepoMapService.update_files(changed_files)
│   │
│   ├── ON RETRIES EXHAUSTED:
│   │   ├── PMAdapter.add_comment(task.task_id, full attempt log + reviewer feedback)
│   │   ├── PMAdapter.update_status(task.task_id, NEEDS_HUMAN_REVIEW)
│   │   └── Write attempt_log + token_usage to local state
│   │
│   └── OTel: close "haive.task" span
│
└── CLI exits after wave completes
    ├── Prints summary: N complete, M needs-human-review, K blocked
    └── Human addresses needs-human-review tasks, re-runs haive run --project <id>

[When done=True on a subsequent run:]
└── VCSAdapter.create_project_pr(project_branch → main)
    CLI exits with success

OTel: close "haive.run" span

Later (batch, separate command):
└── phoenix.evals → scores attached to task spans in Phoenix UI
```

---

## Open Questions

1. ~~**Orchestrator loop termination:**~~ **Resolved.** Orchestrator produces an explicit `done=True` signal. When `done=True`, the CLI calls `VCSAdapter.create_project_pr(project_branch → main)`.

2. ~~**Double-failure escalation:**~~ **Resolved.** Executor exhausts retries → calls `PMAdapter.update_status(NEEDS_HUMAN_REVIEW)` and `PMAdapter.add_comment(attempt summary)`. Orchestrator reads comments on next run and decides whether to create a recovery task. The run never blocks on a single task failure.

3. ~~**Agent registry format:**~~ **Resolved.** YAML validated against a Pydantic schema at load time. On validation failure: print the invalid role name(s) and the validation error(s) to stderr, then exit with a non-zero status code. Do not silently skip — a task that routes to a broken agent would fail at runtime with a confusing error.

4. ~~**Reviewer model tier:**~~ **Resolved.** The Review Agent supports escalation via an `uncertain: bool` signal in `ReviewVerdict`. When `uncertain=True`, the executor advances to the next model in the ordered `REVIEWER_MODELS` list and asks again. The reviewer signals uncertainty when correctness depends on subtle context it can't fully reason about — a more capable model may catch what it missed. If all reviewer models return `uncertain`, the system defaults to `passed=False` and the executor retries on the next executor tier as normal. `REVIEWER_MODELS` is an ordered list from cheapest to most capable (e.g., `haiku,sonnet,opus`).

5. ~~**Project branch naming:**~~ **Resolved.** Convention is `haive/project-{id}`. Simple, collision-free, consistent with task branch naming (`haive/task-{id}`). The project branch is created by haive (via VCSAdapter) if it does not exist.

6. **Auto-merge permissions:** Auto-merging PRs requires the VCS token to have merge permissions and the repository to allow auto-merge. For `GitHubVCSAdapter`, document the required repo settings in the README.

7. ~~**`GitHubPMAdapter` metadata format:**~~ **Resolved.** Structured task metadata is stored as GitHub Projects v2 custom fields (`haive_agent_role`, `haive_complexity`, `haive_lineage_depth`, `haive_recovery_for`, `haive_acceptance_criteria`). See the `GitHubPMAdapter` notes in Section 2 for field types and setup requirements.

---

## Deferred to Later Documents

- Full agent role definitions and system prompts (→ Agent Model doc)
- Task handoff schema and Pydantic model definitions (→ Communication Protocol doc)
- Complete model routing rules and LiteLLM fallback config (→ Model Routing Strategy doc)
- Context budget rules, snippet size limits, dependency output truncation (→ Token Efficiency Strategy doc)
- All Pydantic schema definitions (→ Data and State Model doc)
