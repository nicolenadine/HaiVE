# Haive — Build Plan

## Overview

Each step in this plan represents one milestone of work: focused, independently testable, and small enough to review safely. Steps within a phase may be parallelized where dependencies allow, but are listed in recommended execution order.

---

## Step Index

| Step | Phase | Title |
|------|-------|-------|
| 1 | Foundation | Project Skeleton |
| 2 | Foundation | Config Management and Settings |
| 3 | Foundation | Core Enums |
| 4 | Foundation | Task and State Schemas |
| 5 | Adapters | PM Adapter — Interface and GitHub Implementation (Read) |
| 6 | Adapters | PM Adapter + VCS Adapter — Write |
| 7 | Persistence | State File I/O |
| 8 | Persistence | Agent Registry Loader |
| 9 | Model Routing | LiteLLM Tier Configuration |
| 10 | Orchestration | Orchestrator |
| 11 | Discovery | agent.md Format Spec and Validator |
| 12 | Discovery | FileIndexService — agent.md Generation (`haive index`) |
| 13 | Discovery | Code Discovery Agent |
| 14 | Discovery | FileIndexService — Section Loading |
| 15 | Discovery | FileIndexService — Post-Task Regeneration |
| 16 | Execution | Context Assembler |
| 17 | Execution | Agent Output Schemas and Output Validator |
| 18 | Execution | Agent System Prompts |
| 19 | Execution | Review Agent |
| 20 | Execution | Task Executor |
| 21 | Orchestration | Task Scheduler |
| 22 | Observability | OpenTelemetry and Phoenix |
| 23 | CLI | Harness CLI |
| 24 | Integration | End-to-End Integration Test |

---

## Phase 1: Foundation

### Step 1 — Project Skeleton

**Goal:** A runnable, installable Python package with no agent logic yet.

**Scope**
- `pyproject.toml` — package metadata, all dependencies declared (`litellm`, `pydantic`, `pydantic-settings`, `typer`, `pytest`, `opentelemetry-sdk`, `openinference-instrumentation-litellm`, `arize-phoenix`, `PyGithub`, `filelock`)
- `haive/__init__.py` — package root
- `haive/cli.py` — Typer app with a placeholder `run` command
- `tests/__init__.py` and `tests/conftest.py`
- `README.md` — one paragraph, the `haive run --project <id>` command, and a note to run `haive config create` first

**Success Criteria**
- [ ] `pip install -e .` completes without errors
- [ ] `haive --help` prints the CLI help
- [ ] `haive run --project 1` exits with a "not implemented" message
- [ ] `pytest` runs and exits 0 (no tests yet, just collection passes)

**Startup preflight checks** (added to the CLI entrypoint in this step as stubs, wired to real checks in later steps):
- `git` is on the system `PATH` — required for `VCSAdapter.push_commits`
- Active config exists — required for `Settings` to load
- Exit with a clear, actionable error message if any check fails

**Deferred:** All logic, models, and integrations.

---

### Step 2 — Config Management and Settings

**Goal:** Establish the configuration system — the CLI commands for creating, switching, and editing named configs, and the `Settings` class that loads from whichever config is active.

**Scope**
- `~/.haive/` directory structure, created on first use:
  - `~/.haive/configs/` — named config files (key=value format, same as `.env`)
  - `~/.haive/active` — single line containing the name of the active config
  - `~/.haive/state/` — created here as the intended home for state files (populated in Step 7)
- `haive/config/manager.py` — `ConfigManager` class
  - `create(name: str) -> None` — creates `~/.haive/configs/{name}.env`; errors if name already exists
  - `use(name: str) -> None` — writes name to `~/.haive/active`; errors if config does not exist
  - `set_value(key: str, value: str) -> None` — upserts a `KEY=VALUE` line in the active config
  - `edit() -> None` — opens the active config file in `$EDITOR` (falls back to `nano`)
  - `show() -> dict[str, str]` — reads active config; masks values whose key matches `TOKEN|KEY|SECRET|PASSWORD`
  - `list_configs() -> list[str]` — names of all configs; caller marks the active one
  - `active_config_path() -> str` — path to the active config file; creates and activates `default` if none set
- `haive/cli.py` — `haive config` subcommand group:
  - `haive config create <name>`
  - `haive config use <name>`
  - `haive config set <KEY> <VALUE>`
  - `haive config edit`
  - `haive config show`
  - `haive config list`
- `haive/models/config.py` — `Settings` class using `pydantic-settings`
  - Loads from `ConfigManager.active_config_path()`
  - All fields: tier model lists, max attempts, context budgets, `ORCHESTRATOR_MODEL`, `REVIEWER_MODELS`, `MAX_EXECUTORS`, `MAX_RECOVERY_DEPTH`, API keys, `GITHUB_TOKEN`, `GITHUB_REPO`
  - Startup validation: missing required fields raise `ValidationError` with the config file path in the message so the user knows where to look

**Success Criteria**
- [ ] `haive config create myproject` creates `~/.haive/configs/myproject.env`
- [ ] `haive config use myproject` makes subsequent `haive config show` display `myproject`'s values
- [ ] `haive config use nonexistent` fails with a clear message listing available configs
- [ ] `haive config set GITHUB_REPO owner/repo` persists to the active config file
- [ ] `haive config set GITHUB_TOKEN ghp_xxx` appears as `GITHUB_TOKEN=***` in `haive config show`
- [ ] `haive config edit` opens `$EDITOR` with the active config file
- [ ] `haive config list` marks the active config with a visual indicator
- [ ] No active config set → `default` is created and activated automatically
- [ ] `Settings()` loads from the active config path
- [ ] A missing `GITHUB_TOKEN` raises `ValidationError` naming the config file path
- [ ] `TIER_LOW_MODELS=ollama/mistral,ollama/llama3` parses as `["ollama/mistral", "ollama/llama3"]`

**Deferred:** No `haive run` yet.

---

### Step 3 — Core Enums

**Goal:** Define the shared vocabulary used across all schemas.

**Scope**
- `haive/models/enums.py` — `TaskStatus`, `AgentRole`, `Complexity` (all values from the data model doc)
- Unit tests: all enum values present, enum serializes to lowercase string, enum deserializes from string

**Success Criteria**
- [ ] `TaskStatus.IN_PROGRESS` serializes to `"in_progress"`
- [ ] `AgentRole("scaffold_agent")` deserializes correctly
- [ ] All 10 agent roles present in `AgentRole`
- [ ] All 6 task statuses present in `TaskStatus`
- [ ] All 3 complexity levels present in `Complexity`

**Deferred:** No task or state models yet.

---

### Step 4 — Task and State Schemas

**Goal:** Define the core data contracts for execution records, verdicts, and the local state file.

**Scope**
- `haive/models/task.py` — `Task`, `Project`, `TaskComment`, `AttemptLogEntry`, `VerdictSummary`, `TokenUsage`, `TaskExecutionRecord`
- `haive/models/state.py` — `ProjectState` (includes `schema_version: str = "1"` and `last_run_at: datetime | None = None`)
- `haive/models/verdict.py` — `ReviewVerdict`
- Unit tests: create a `ProjectState` with five `TaskExecutionRecord` entries, serialize to JSON, deserialize and verify round-trip fidelity

**Key invariants to test**
- `VerdictSummary` contains only `passed` and `reason` — no `suggestions`
- `AttemptLogEntry` has no `suggestions` field
- `ProjectState.tasks` is `dict[str, TaskExecutionRecord]` keyed by `task_id`
- `ProjectState` contains no task descriptions, titles, or acceptance criteria
- `ProjectState.schema_version` mismatch raises a clear error on load (not a cryptic Pydantic error)

**Success Criteria**
- [ ] A `ProjectState` with five `TaskExecutionRecord` entries serializes to valid JSON
- [ ] Deserialized `ProjectState` is equal to the original
- [ ] `AttemptLogEntry` has no `suggestions` field (verify by inspection and schema test)
- [ ] `ReviewVerdict` has `suggestions`; `VerdictSummary` does not
- [ ] Loading a state file with a mismatched `schema_version` raises a descriptive error

**Deferred:** GitHub models, context pack models, orchestrator models.

---

## Phase 2: Adapters

### Step 5 — PM Adapter — Interface and GitHub Implementation (Read)

**Goal:** Define the `PMAdapter` protocol and implement its read operations in `GitHubPMAdapter`.

**Scope**
- `haive/adapters/pm/base.py` — `PMAdapter` protocol (all methods defined, no implementation)
- `haive/adapters/pm/github.py` — `GitHubPMAdapter` read methods:
  - `get_project(project_id: str) -> Project`
  - `get_tasks(project_id: str) -> list[Task]` — reads GitHub Issues + all Project fields (status, blocked_by, and the five `haive_*` custom fields) via GraphQL; maps to domain `Task` objects
  - `read_new_comments(project_id: str, since: datetime) -> list[TaskComment]` — reads comments across all Issues in the project since `since`
  - Startup validation: query the Project's field schema; exit with a clear error listing any missing `haive_*` custom fields
- Uses `PyGithub` for Issues/Milestones; GitHub GraphQL API for Project field reads and custom field values
- Credentials from `Settings.github_token`, `Settings.github_repo`, `Settings.github_project_id`
- Unit tests: mock PyGithub and GraphQL responses; verify `get_tasks` correctly maps custom field values to domain `Task` fields; verify startup validation detects a missing custom field; verify `read_new_comments` filters by `since`

**Success Criteria**
- [ ] `get_project("7")` returns a `Project` with title, description, project_branch
- [ ] `get_tasks("7")` returns all tasks as domain `Task` objects with correct `agent_role`, `complexity`, `depends_on`, `acceptance_criteria` read from GitHub Projects custom fields
- [ ] `read_new_comments` returns only comments created after `since`, across all project Issues
- [ ] Startup with a missing `haive_complexity` field exits with an error naming the missing field
- [ ] No component outside `haive/adapters/` imports `PyGithub`
- [ ] Tests use mocks; no real GitHub API calls in CI

**Deferred:** Write operations.

---

### Step 6 — PM Adapter + VCS Adapter — Write

**Goal:** Implement write operations for both adapters, completing the full `PMAdapter` and `VCSAdapter` protocols.

**Scope**
- `haive/adapters/pm/github.py` — `GitHubPMAdapter` write methods:
  - `create_task(project_id: str, task: NewTask) -> str` — creates GitHub Issue with human-readable body; sets all five `haive_*` custom fields via GraphQL; returns `task_id`
  - `set_dependency(task_id: str, depends_on: list[str]) -> None` — sets native GH "blocked by" relationships
  - `update_status(task_id: str, status: TaskStatus) -> None` — updates GitHub Project status field via GraphQL
  - `add_comment(task_id: str, body: str) -> None`
- `haive/adapters/vcs/base.py` — `VCSAdapter` protocol (all methods defined, no implementation)
- `haive/adapters/vcs/github.py` — `GitHubVCSAdapter`:
  - `create_branch(branch_name: str, base_branch: str) -> None` — PyGithub API
  - `push_commits(branch: str, changed_files: list[str], message: str) -> None` — runs `git add <files> && git commit -m "<message>" && git push origin <branch>` via subprocess; atomic single commit for all changed files
  - `create_pr(title: str, body: str, head_branch: str, base_branch: str) -> str` — returns `pr_id`; PyGithub API
  - `merge_pr(pr_id: str) -> None` — enables auto-merge (merges when CI passes, or immediately if no CI); PyGithub API
  - `add_pr_comment(pr_id: str, body: str) -> None`
  - `create_project_pr(head_branch: str, base_branch: str, title: str, body: str) -> str`
- Unit tests: mock all write operations and subprocess calls; verify correct arguments passed
- Integration note: document required GitHub token permissions and repo settings (auto-merge must be enabled); `git` must be on system `PATH`

**Success Criteria**
- [ ] `create_task` creates a GitHub Issue with a human-readable body and all five `haive_*` custom fields set
- [ ] `set_dependency` sets the native GitHub "blocked by" relationship
- [ ] `update_status` updates the Issue's `status` in the GitHub Project via GraphQL
- [ ] `create_branch` creates a branch off the specified base
- [ ] `push_commits` runs `git add/commit/push` via subprocess (mocked in tests) and produces a single commit
- [ ] `create_pr` creates a PR and returns a `pr_id`
- [ ] `merge_pr` enables auto-merge on the PR
- [ ] No component outside `haive/adapters/` imports `PyGithub`
- [ ] All tests pass with mocks; no real writes in CI

**Deferred:** No real end-to-end adapter integration test yet.

---

## Phase 3: Persistence

### Step 7 — State File I/O

**Goal:** Persist and load `ProjectState` (internal eval/audit data) to/from disk with safe concurrent writes.

**Scope**
- `haive/persistence/state_store.py` — `StateStore` class
  - `load_or_init(project_id: str) -> ProjectState`
  - `save(state: ProjectState) -> None` — atomic write with file lock
  - `merge_task_record(task_id: str, record: TaskExecutionRecord) -> None` — thread-safe merge of one task's results
  - State file path: `~/.haive/state/{owner}/{repo}/project_{id}.json` — `owner/repo` derived from `Settings.github_repo`
  - On load: check `schema_version`; if mismatched, raise a descriptive error (not a Pydantic error)
- File locking: use `filelock` library to serialize concurrent writes
- Write pattern: read current state → merge update → write full file while lock is held
- Unit tests:
  - Load-or-init creates a new file when none exists
  - Save + load round-trips correctly
  - Two concurrent `merge_task_record` calls do not corrupt the file (use threading in test)
  - Load of a state file with wrong `schema_version` raises a clear error

**Success Criteria**
- [ ] `load_or_init("7")` creates `~/.haive/state/owner/repo/project_7.json` if it does not exist
- [ ] `save()` writes valid JSON and `load_or_init()` restores it exactly
- [ ] Concurrent writes from two threads produce a valid state file (both records present)
- [ ] State file directory is created if it does not exist
- [ ] State file does not contain task status or task descriptions (those live in the PM tool)
- [ ] Schema version mismatch raises a descriptive error naming the file path and versions

**Deferred:** No orchestrator or executor integration yet.

---

### Step 8 — Agent Registry Loader

**Goal:** Load and validate the agent registry at startup; derive the orchestrator's compact summary.

**Scope**
- `agents.yaml` — complete registry with all 10 agents (descriptions, skills, system_prompt paths, output_schema paths, max_tokens, retry_limit, prompt_version)
- `haive/models/config.py` addition — `AgentConfig` Pydantic model
- `haive/registry/agent_registry.py` — `AgentRegistry` class
  - `load(path: str) -> AgentRegistry` — validates YAML on load; crashes with clear error on invalid config
  - `get_agent(role: AgentRole) -> AgentConfig`
  - `get_orchestrator_summary() -> str` — one line per agent derived from description + skills
- Unit tests:
  - Valid registry loads all 10 agents
  - Missing required field raises on load
  - Unknown agent role raises on load
  - Orchestrator summary contains one line per agent

**Success Criteria**
- [ ] `AgentRegistry.load("agents.yaml")` succeeds with the complete registry
- [ ] A YAML file with a missing `description` field causes a startup crash with a readable message
- [ ] `get_orchestrator_summary()` returns a string with exactly 10 lines
- [ ] Prompt file paths in the registry are noted as relative — not validated for existence at this step

**Deferred:** Prompt file existence check deferred to Step 18.

---

## Phase 4: Model Routing

### Step 9 — LiteLLM Tier Configuration

**Goal:** Make model calls through the correct tier with within-tier fallback, and distinguish API errors from bad-output failures.

**Scope**
- `haive/llm/tier.py` — `Tier` dataclass (models list, max_attempts, context_budget)
- `haive/llm/model_client.py` — `ModelClient` class
  - `call(tier: Tier, prompt: str, system: str, max_tokens: int) -> str`
  - LiteLLM handles within-tier model fallback transparently
  - API errors (rate limit, timeout, 500) propagate as `APIError` — caller decides whether to retry
  - Returns raw string response
- `haive/llm/tier_config.py` — `TierConfig` built from `Settings`; maps `Complexity` → `Tier`
- `haive/llm/token_counter.py` — `TokenCounter` class
  - `estimate(text: str) -> int` — `math.ceil(len(text) / 4)` — model-agnostic, no external dependencies
  - Used by `CodeDiscoveryAgent.discover` (Step 13), `FileIndexService.load_sections` (Step 14), and `ContextAssembler` (Step 16) to enforce token budgets
- Unit tests: mock `litellm.completion`, verify correct model list passed, verify fallback on first model failure, verify `APIError` is not swallowed

**Success Criteria**
- [ ] `ModelClient.call(tier=TIER_LOW, ...)` calls `litellm.completion` with `TIER_LOW_MODELS`
- [ ] If the first model in the tier fails with a rate limit, LiteLLM tries the second — no explicit retry code in `ModelClient`
- [ ] `APIError` is raised (not swallowed) when all models in a tier are unavailable
- [ ] `Complexity.LOW` maps to `TIER_LOW`, `MEDIUM` to `TIER_MEDIUM`, `HIGH` to `TIER_HIGH`
- [ ] `TokenCounter.estimate("hello world")` returns `3` (11 chars, `ceil(11/4) = 3`)
- [ ] `TokenCounter` imports neither `tiktoken` nor `litellm`

**Deferred:** Retry loop logic deferred to the Task Executor step.

---

## Phase 5: Orchestration

### Step 10 — Orchestrator

**Goal:** Implement the coordinator that reads task statuses and produces the next batch of tasks to create.

**Scope**
- `haive/models/orchestrator.py` — `OrchestratorInput`, `OrchestratorTaskView`, `OrchestratorOutput`, `NewTask`
  - `NewTask.depends_on: list[str]` supports two formats:
    - Existing task IDs: `"42"` (GitHub issue number of an already-created task)
    - Intra-wave positional refs: `"new:0"`, `"new:1"` — zero-based index into the current `new_tasks` list
  - This allows the orchestrator to express a full dependency graph in one wave; the CLI resolves refs during creation (see Step 23)
- `haive/orchestration/orchestrator.py` — `Orchestrator` class
  - `run_loop(input: OrchestratorInput) -> OrchestratorOutput`
  - Calls `ModelClient` with `ORCHESTRATOR_MODEL`
  - Validates response against `OrchestratorOutput` schema
  - The orchestrator prompt must document the `"new:N"` intra-wave ref convention so the LLM knows how to express within-wave dependencies
  - Recovery logic: if a task is `needs-human-review` with human comments and `lineage_depth < MAX_RECOVERY_DEPTH`, produce a recovery `NewTask` with `recovery_for` set and `lineage_depth` incremented
  - No `EscalationSignal` — escalation happens automatically in the executor; orchestrator only sees the resulting `needs-human-review` status and decides whether to attempt recovery
  - `done: bool` output: when True, `new_tasks` must be empty
  - Treat empty `new_tasks` + `done=False` as a configuration error
- `haive/orchestration/task_view_builder.py` — `TaskViewBuilder`
  - `build(tasks: list[Task], local_state: ProjectState, budget_tokens: int) -> list[OrchestratorTaskView]`
  - Merges domain `Task` data with local state verdict and attempt_log
  - Drops `attempt_log` from old complete tasks for token efficiency
- Unit tests:
  - Fresh project with no tasks: orchestrator produces first wave of `new_tasks`
  - Task in `needs-human-review` with human comment within `MAX_RECOVERY_DEPTH`: recovery task produced with `lineage_depth + 1`
  - Task in `needs-human-review` at `MAX_RECOVERY_DEPTH`: no recovery task; `done=False` with remaining unblocked tasks
  - `done=True` is produced when all tasks are complete
  - Human comment is present in `OrchestratorInput.new_comments`

**Success Criteria**
- [ ] `OrchestratorOutput` validates correctly (no model names, no file paths, no task bodies in output)
- [ ] Recovery task has `recovery_for` set to the failed task's `task_id`
- [ ] `lineage_depth` increments correctly across recovery generations
- [ ] Empty `new_tasks` + `done=False` raises a runtime error
- [ ] Tests use mocked LLM — no real model calls

**Deferred:** No multi-run integration yet; that comes with the CLI.

---

## Phase 6: Code Discovery & Indexing

> **Note:** Steps 11–15 were originally implemented as a DuckDB + tree-sitter dependency graph with PageRank-style ranking (`haive/repomap/db.py`, `graph.py`, `repo_map_service.py`, `language_parser.py`). That implementation is retired in favor of the agentic Code Discovery Agent + `agent.md` index design below — see `planning_docs/decisions.md` ("Agentic Code Discovery Agent replaces the structural repo graph" and related entries) for the rationale. When this phase is (re)implemented, the `haive/repomap/` module and its tests should be removed.

### Step 11 — agent.md Format Spec and Validator

**Goal:** Define the structural format for per-directory `agent.md` index files and a pure-Python validator that checks generated files against that format.

**Scope**
- `planning_docs/agent_md_spec.md` — exact format: required section headers (e.g. `## Files` listing `path — one-line description`; optional `## Key Symbols` listing `name (kind) — start-end`), per-line format rules, no prose paragraphs, a maximum line count
- `haive/discovery/agent_md.py` — `AgentMdValidator` class
  - `validate(content: str) -> list[str]` — returns a list of violation messages; an empty list means valid
  - Checks: required section headers present, each file/symbol entry matches the expected line format, no line resembling a prose paragraph (vs. a recognized list-item pattern), total line count within the configured limit
- Unit tests: a correctly formatted `agent.md` returns no violations; a missing required section is flagged; a prose paragraph is flagged; an oversized file is flagged

**Success Criteria**
- [ ] A correctly formatted `agent.md` returns no violations
- [ ] A missing `## Files` section is flagged with a specific message
- [ ] A prose paragraph is flagged as a violation
- [ ] `AgentMdValidator` has no LLM dependency — pure string/regex logic, fully deterministic

**Deferred:** Generation logic (Step 12).

---

### Step 12 — FileIndexService: agent.md Generation (`haive index`)

**Goal:** Generate per-directory `agent.md` files for the whole repo using a low-tier LLM, validated against the Step 11 spec.

**Scope**
- `haive/discovery/file_index_service.py` — `FileIndexService` class
  - `generate_all(root: str) -> None` — walks the repo respecting `.gitignore` (same directory-pruning behavior as the retired `RepoMapService` scanner: `.git` is the only hardcoded exclusion, everything else comes from `.gitignore`); for each directory containing at least one source file, calls the low-tier `ModelClient` to draft an `agent.md` describing that directory's files and subdirectories, validates the draft via `AgentMdValidator`, retries (bounded) on violation, then writes the file
  - Model tier: routed through the existing named-config tier system, defaulting to the lowest tier
- `haive/cli.py` — `haive index` command: calls `generate_all()`
- `haive/cli.py` — `haive index --validate` flag: runs `AgentMdValidator` against all existing `agent.md` files without regenerating, prints any violations found
- Unit tests (mocked LLM): generation produces a valid `agent.md` for a fixture directory; a validation failure triggers one retry that then succeeds; exhausted retries raise a clear error; `.gitignore`-excluded directories produce no `agent.md`

**Success Criteria**
- [ ] `haive index` generates one `agent.md` per source directory in a fixture repo
- [ ] Generated `agent.md` files pass `AgentMdValidator` with zero violations
- [ ] A mocked LLM response that fails validation triggers a retry, succeeding on the second attempt
- [ ] `.gitignore`-excluded directories produce no `agent.md`
- [ ] `haive index --validate` reports violations in existing files without calling the LLM

**Deferred:** Post-task incremental regeneration (Step 15); discovery/consumption of `agent.md` files (Step 13).

---

### Step 13 — Code Discovery Agent

**Goal:** An agentic, tool-calling LLM agent that navigates the `agent.md` tree to find task-relevant files and sections, under strict guardrails.

**Scope**
- `haive/models/discovery.py` — `DiscoveredSection` (`file: str`, `symbol: str | None`, `start_line: int | None`, `end_line: int | None`, `full: bool`, `reason: str`); `DiscoveryResult` (`sections: list[DiscoveredSection]`, `status: Literal["found", "empty"]`)
- `haive/discovery/code_discovery_agent.py` — `CodeDiscoveryAgent` class
  - `discover(task: Task, root: str, token_budget: int) -> DiscoveryResult`
  - Tools exposed to the agent: `read_agent_md(directory: str) -> str`, `list_subdirectories(directory: str) -> list[str]`
  - System prompt enforces guardrails: max exploration depth, max tool-call count, must respect `token_budget` when selecting sections, must return output matching `DiscoveryResult`
  - Starts at the repo root's `agent.md`; descends into a subdirectory only when its parent's `agent.md` suggests relevance
  - Model tier: low tier (same routing as Step 12)
- Unit tests (mocked LLM/tool calls): given a two-level fixture tree, the agent finds the directly relevant file without reading unrelated sibling subdirectories; a guardrail test where the agent attempts to exceed max depth/call count is cut off and returns its best-effort result rather than erroring; a no-match case returns `status="empty"`

**Success Criteria**
- [ ] Given a task naming a feature present in only one subdirectory, discovery returns that subdirectory's file(s) without reading sibling subdirectories' `agent.md` files
- [ ] Exceeding the configured max tool-call count stops exploration and returns the best result so far, not an error
- [ ] No relevant files found → `DiscoveryResult(sections=[], status="empty")`, not an exception
- [ ] Output is validated against `DiscoveryResult` via the existing `OutputValidator` pattern

**Deferred:** Section loading and slicing (Step 14).

---

### Step 14 — FileIndexService: Section Loading

**Goal:** Turn a `DiscoveryResult` into actual loaded source content, ready for the (I/O-free) Context Assembler.

**Scope**
- `haive/models/discovery.py` addition — `LoadedSection` (`file: str`, `source: str`, `reason: str`)
- `FileIndexService.load_sections(result: DiscoveryResult, root: str) -> list[LoadedSection]`
  - For `full=True` entries: read the whole file
  - For `start_line`/`end_line` entries: read the file and slice `lines[start_line - 1 : end_line]` directly — no parsing needed
  - This is the only file-content read in the discovery pipeline; `ContextAssembler` (Step 16) receives `list[LoadedSection]` as a parameter and performs no I/O itself
- Unit tests: a `full=True` section returns the entire file content; a `start_line`/`end_line` section returns exactly that range; a discovery entry pointing at a file that no longer exists raises a descriptive error rather than silently skipping

**Success Criteria**
- [ ] `full=True` returns the complete file content
- [ ] A `start_line`/`end_line` section returns exactly those lines, no more
- [ ] A discovery entry pointing at a missing file raises a descriptive error

**Deferred:** Regeneration trigger (Step 15).

---

### Step 15 — FileIndexService: Post-Task Regeneration

**Goal:** Keep `agent.md` files in sync automatically after each task, without a startup scan.

**Scope**
- `FileIndexService.update_after_task(changed_files: list[str], root: str) -> None`
  - Called by the Task Executor after a task's changes are committed, using git output as the source of truth (`get_changed_files`) — not agent self-reporting
  - Maps each changed file to its containing directory; regenerates only the `agent.md` files for directories with at least one changed file (a file add/delete also updates the parent directory's listing)
  - Each regenerated `agent.md` goes through the same generate → validate → retry path as `generate_all` (Step 12)
- `haive/discovery/git_utils.py` — `get_changed_files(repo_root: str) -> list[str]` — runs `git diff --name-only` and `git status --porcelain`
- Unit tests: changing one file regenerates only its directory's `agent.md`, not unrelated directories; adding a new file updates the directory's listing; deleting a file removes its entry

**Success Criteria**
- [ ] Editing a file in `dir/` regenerates `dir/agent.md` only
- [ ] Adding a new file to a directory results in that file appearing in the regenerated `agent.md`
- [ ] Deleting a file removes its entry from the regenerated `agent.md`
- [ ] `get_changed_files` is driven by git output, not agent-reported file lists

**Deferred:** None — this closes the loop opened in Step 12. No startup scan is ever performed; `haive run` only reads existing `agent.md` files (see Step 23).

---

## Phase 7: Execution Pipeline

### Step 16 — Context Assembler

**Goal:** Build the agent prompt from a context pack and task definition.

**Scope**
- `haive/execution/context_assembler.py` — `ContextAssembler` class
  - `assemble(task: Task, loaded_sections: list[LoadedSection], discovery_status: Literal["found", "empty_expected", "empty_unexpected"], agent_config: AgentConfig, dependency_outputs: dict[str, str], retry_feedback: list[str] | None) -> str`
  - Assembly order: system prompt → task description + acceptance criteria → discovered sections (or, when `loaded_sections` is empty, an explicit "no existing relevant code was found for this task" note) → dependency outputs → reviewer feedback (if retry)
  - No service calls and no file I/O — receives all data as parameters; `FileIndexService` (Steps 13–14) has already done any file reading
  - Token budget is enforced upstream by `CodeDiscoveryAgent`/`FileIndexService`; this step formats what was returned
- Unit tests:
  - Retry feedback appears in the prompt when provided
  - Dependency outputs are included in correct order
  - System prompt content is present
  - Empty `loaded_sections` produces the explicit "no relevant code found" note instead of a blank section

**Success Criteria**
- [ ] A prompt assembled for a retry includes the reviewer's suggestions
- [ ] A prompt for a first attempt has no feedback section
- [ ] Dependency outputs from `depends_on` tasks appear in the prompt
- [ ] An empty discovery result produces the explicit no-context note in the prompt
- [ ] The assembled string contains all required sections in the documented order

**Deferred:** No LLM call here — just prompt construction.

---

### Step 17 — Agent Output Schemas and Output Validator

**Goal:** Define structured output contracts for all agent roles and validate LLM responses against them.

**Scope**
- `haive/models/agent_output.py`:
  - `FileToCreate`, `ScaffoldAgentOutput`
  - `FileEdit`, `CodeEditorOutput` (used by `implementation_agent`, `refactoring_agent` too)
  - `ReviewAgentOutput`
  - Stub schemas for remaining agents: `ApiIntegrationAgentOutput`, `DatabaseAgentOutput`, `TestGeneratorOutput`, `CodeReviewerOutput`, `SecurityReviewerOutput`, `DocumentationWriterOutput` (using `CodeEditorOutput` pattern or findings-list)
- `schemas/` directory — JSON schema files generated from each Pydantic model
- `haive/execution/output_validator.py` — `OutputValidator` class
  - `validate(raw: str, role: AgentRole) -> BaseModel` — extract JSON from raw text, validate against the role's schema
  - Returns the parsed Pydantic model on success
  - Raises `OutputValidationError` on failure (schema mismatch or unparseable JSON)
- Unit tests:
  - Valid JSON for each role parses correctly
  - JSON embedded in markdown code block is extracted
  - Invalid JSON raises `OutputValidationError`
  - Extra fields are rejected (strict mode)

**Success Criteria**
- [ ] All 10 agent output schemas are defined and registered
- [ ] JSON schemas generated in `schemas/` match the Pydantic models
- [ ] `OutputValidator.validate` handles JSON wrapped in ` ```json ``` ` markdown fences
- [ ] `OutputValidationError` contains the role name and the raw string for debugging

**Deferred:** Review agent schema integration deferred to Step 19.

---

### Step 18 — Agent System Prompts

**Goal:** Write system prompts for all 10 agents following the documented five-section template.

**Scope**
- `prompts/scaffold_agent.md`
- `prompts/implementation_agent.md`
- `prompts/code_editor.md`
- `prompts/refactoring_agent.md`
- `prompts/api_integration_agent.md`
- `prompts/database_agent.md`
- `prompts/test_generator.md`
- `prompts/code_reviewer.md`
- `prompts/security_reviewer.md`
- `prompts/documentation_writer.md`
- `prompts/archive/` directory structure (empty at this stage)
- `guidelines.md` — project coding guidelines for the Review Agent
- Each prompt must include: Role, What You Receive, Constraints, Output Format, Quality Bar
- Validate that all `system_prompt` paths in `agents.yaml` exist at load time (add to `AgentRegistry.load`)

**Success Criteria**
- [ ] All 10 prompt files exist and follow the five-section template
- [ ] Each prompt's Constraints section explicitly lists what the agent must NOT do
- [ ] Each prompt's Output Format section references the correct output schema
- [ ] `AgentRegistry.load` raises an error if a prompt file path does not exist
- [ ] `guidelines.md` exists and is referenced by the Review Agent prompt

**Deferred:** Prompt quality is iteratively improved — this step establishes structure, not perfection.

---

### Step 19 — Review Agent

**Goal:** Implement the LLM-as-judge that evaluates sub-agent output quality.

**Scope**
- `haive/execution/review_agent.py` — `ReviewAgent` class
  - `review(task: Task, agent_output: BaseModel, loaded_sections: list[LoadedSection], discovery_status: Literal["found", "empty_expected", "empty_unexpected"], discovery_note: str) -> ReviewVerdict`
  - Builds the review prompt: task description, acceptance criteria, agent output, the discovered sections the task agent was given, `discovery_status`/`discovery_note`, guidelines
  - When `discovery_status="empty_unexpected"`, the prompt explicitly flags this for extra scrutiny — the agent output may assume context it never received
  - Calls `ModelClient` with the current reviewer model (advances through `REVIEWER_MODELS` on `uncertain`)
  - Validates response against `ReviewAgentOutput` schema
  - Returns `ReviewVerdict` with `passed`, `reason`, `suggestions`, `uncertain`
- `REVIEWER_MODELS` is an ordered list from least to most capable (e.g., `haiku,sonnet,opus`). The executor advances through this list when `uncertain=True`. If all reviewer models return `uncertain`, defaults to `passed=False`.
- `uncertain=True` and `passed=True` are mutually exclusive — validate at schema level
- `uncertain` does not consume an executor retry
- Unit tests:
  - Passing output returns `ReviewVerdict(passed=True, suggestions=[], uncertain=False)`
  - Failing output returns `ReviewVerdict(passed=False, reason=..., suggestions=[...], uncertain=False)`
  - Uncertain output returns `ReviewVerdict(uncertain=True)` → executor advances reviewer model
  - All reviewer models return `uncertain` → defaults to `passed=False`
  - `discovery_status="empty_unexpected"` is present in the review prompt
  - `discovery_status="empty_expected"` (e.g. a scaffold task) does not trigger the extra-scrutiny note
  - `suggestions` is never empty when `passed=False` and `uncertain=False`

**Success Criteria**
- [ ] `review()` accepts any agent output type (polymorphic via `BaseModel`)
- [ ] `ReviewVerdict.suggestions` is non-empty when `passed=False` and `uncertain=False`
- [ ] `uncertain=True` with `passed=True` raises a validation error
- [ ] `VerdictSummary` is correctly derived from `ReviewVerdict` (no suggestions leaked)
- [ ] `discovery_status="empty_unexpected"` is included in the review prompt as an explicit signal for extra scrutiny
- [ ] Reviewer model advancement on `uncertain` is tested without real LLM calls
- [ ] Tests use mocked LLM — no real model calls

---

### Step 20 — Task Executor

**Goal:** Implement the full lifecycle of a single task: branch creation → context assembly → LLM call → validation → review → PR submission and auto-merge (or needs-human-review flagging).

**Scope**
- `haive/execution/task_executor.py` — `TaskExecutor` class
  - `run(task: Task, project_state: ProjectState, discovery_agent: CodeDiscoveryAgent, file_index: FileIndexService, registry: AgentRegistry, pm: PMAdapter, vcs: VCSAdapter, settings: Settings) -> TaskExecutionRecord`
  - Implements the full retry/escalation loop:
    - `VCSAdapter.create_branch(f"haive/task-{task.task_id}", base=project_branch)`
    - `PMAdapter.update_status(task.task_id, IN_PROGRESS)`
    - Call `discovery_agent.discover(task, root, token_budget)` → `DiscoveryResult`
    - Determine `discovery_status`: `"found"` if sections were returned; otherwise `"empty_expected"` if `task.agent_role` is a scaffold-type role, else `"empty_unexpected"`
    - Call `file_index.load_sections(result, root)` → `list[LoadedSection]`
    - Assemble prompt via `ContextAssembler` (task description + acceptance criteria + dependency summaries + loaded sections + discovery_status)
    - Call `ModelClient` for current tier
    - Validate output via `OutputValidator` (schema fail → retry or escalate; no Review Agent call)
    - Review output via `ReviewAgent`, passing `loaded_sections`, `discovery_status`, and a short `discovery_note`
    - On pass: apply file changes to disk, commit, `VCSAdapter.create_pr(...)`, `VCSAdapter.add_pr_comment(...)`, `VCSAdapter.merge_pr(pr_id)`, `PMAdapter.update_status(COMPLETE)`, call `file_index.update_after_task(get_changed_files(root), root)`, write `TaskExecutionRecord` to state
    - On fail: increment attempt; escalate tier when attempts exhausted
    - On tier ladder exhausted: `PMAdapter.add_comment(task.task_id, attempt_summary)`, `PMAdapter.update_status(NEEDS_HUMAN_REVIEW)`, write `TaskExecutionRecord` to state
  - Handles the three failure modes distinctly (API error, bad output, tier exhausted)
  - Applies `FileEdit` and `FileToCreate` outputs to disk; `FileEdit` tie-breaking rule: raise `AmbiguousEditError` if `old_string` appears more than once — require surrounding context lines
- Unit tests:
  - Pass on first attempt: branch created, PR submitted, merged, task marked complete
  - Retry with feedback: review fails, suggestions injected into second attempt
  - Tier escalation: medium tier exhausted, escalates to high tier with feedback
  - All tiers exhausted: comment written with full attempt log, task marked needs-human-review
  - Schema failure does not invoke Review Agent
  - Empty discovery on a non-scaffold task produces `discovery_status="empty_unexpected"`, passed through to the Review Agent
  - Empty discovery on a scaffold task produces `discovery_status="empty_expected"`
  - `changed_files` from `git diff`, not agent self-report; passed to `file_index.update_after_task` on success

**Success Criteria**
- [ ] A task that passes produces a `TaskExecutionRecord` with `verdict.passed=True` and a valid `pr_id`
- [ ] Reviewer suggestions appear in the context of the next attempt
- [ ] `AttemptLogEntry` is populated for every attempt, including tier and reason
- [ ] API errors do not consume a retry budget
- [ ] On retries exhausted: PM comment contains the full attempt log; task status is `needs-human-review`
- [ ] `changed_files` is populated from `git diff --name-only`, not from agent self-report
- [ ] On success, `file_index.update_after_task` is called with the git-derived `changed_files`
- [ ] Ambiguous `FileEdit` (duplicate `old_string`) raises `AmbiguousEditError`

**Deferred:** Parallel execution deferred to Task Scheduler.

---

## Phase 8: Task Scheduler

### Step 21 — Task Scheduler

**Goal:** Manage concurrent task execution by reading tasks via `PMAdapter`, evaluating the dependency graph, and managing an executor pool.

**Scope**
- `haive/orchestration/task_scheduler.py` — `TaskScheduler` class
  - `start(tasks: list[Task], state_store: StateStore, pm: PMAdapter, vcs: VCSAdapter, executor_factory: Callable, settings: Settings) -> None`
  - Dependency resolution using `Task.depends_on` and `Task.status` (DAG traversal):
    - `ready`: status `pending` + all `depends_on` task_ids have status `complete`
    - `waiting`: status `pending` + at least one `depends_on` task is `in_progress`
    - `blocked`: status `pending` + at least one `depends_on` task is `needs-human-review`
  - Executor pool: `asyncio.Semaphore(MAX_EXECUTORS)`; spawn executor for each ready task
  - On executor completion: executor has already updated status via `PMAdapter`; re-read tasks, re-evaluate graph, spawn newly-unblocked tasks
  - On `needs-human-review`: mark downstream tasks `blocked` (via `PMAdapter.update_status`), continue independent tasks
  - State writes via `StateStore.merge_task_record` (file locking per Step 7)
  - `asyncio.to_thread()` wrapper around `TaskExecutor.run` (synchronous) to fit the async executor pool
- Unit tests (using mocked `Task` lists and `PMAdapter`, not real API):
  - Five independent tasks: all five start concurrently (up to `MAX_EXECUTORS`)
  - Chain A → B: B does not start until A has status `complete`
  - Chain A → B where A becomes `needs-human-review`: B is marked `blocked`
  - Mixed graph: independent tasks run while a dependent task is waiting

**Success Criteria**
- [ ] `MAX_EXECUTORS=2` cap: at most 2 executors run simultaneously
- [ ] A task whose `depends_on` task is `needs-human-review` transitions to `BLOCKED`, not ready
- [ ] Independent tasks continue running when one task becomes `needs-human-review`
- [ ] All tasks complete before `start()` returns (or all are blocked/needs-human-review)

**Deferred:** Integration with the full run loop deferred to CLI step.

---

## Phase 9: Observability

### Step 22 — OpenTelemetry and Phoenix

**Goal:** Emit structured spans for every meaningful event in the system.

**Scope**
- `haive/observability/setup.py` — `setup_observability(settings: Settings) -> None`
  - Register `openinference-instrumentation-litellm` auto-instrumentation
  - Configure OTLP exporter pointing to Phoenix (URL from `.env`)
  - Create the root `Tracer` for custom spans
- `haive/observability/spans.py` — span helpers
  - `task_span(task: Task)` — context manager; sets `task.id`, `task.role`, `task.complexity`
  - `run_span(project_id: str)` — context manager for the full harness run
  - Span attributes from the architecture doc: `attempt.number`, `tier.name`, `tier.model_used`, `verdict.passed`, `agent.prompt_version`
- Instrument `TaskExecutor.run` with `task_span`
- Instrument the harness run loop with `run_span`
- Unit tests:
  - `setup_observability` registers the OTLP exporter without raising
  - `task_span` emits a span with the required attributes (use OTel test exporter)

**Success Criteria**
- [ ] Running a task produces an OTel span with `task.id`, `task.role`, and `verdict.passed`
- [ ] LiteLLM calls produce spans automatically (auto-instrumentation active)
- [ ] Changing `PHOENIX_OTLP_ENDPOINT` in `.env` changes the export target with no code changes
- [ ] `setup_observability` is idempotent (safe to call multiple times in tests)

**Deferred:** `phoenix.evals` batch eval deferred — not required for core functionality.

---

## Phase 10: CLI

### Step 23 — Harness CLI

**Goal:** Wire all components into a single runnable command.

**Scope**
- `haive/cli.py` — `haive run --project <id>` command (replace the placeholder from Step 1)
- `haive/cli.py` — `haive index` and `haive index --validate` commands (carried over from Step 12; documented here as part of the full CLI surface)
- Startup preflight check added to `haive run`: if the repo root has no `agent.md` files, exit with a clear error instructing the user to run `haive index` first. `haive run` never generates or regenerates `agent.md` files itself — generation happens only via `haive index` (initial) and `FileIndexService.update_after_task` (post-task); there is no startup scan (see `planning_docs/decisions.md`)
- Run sequence (one invocation = one wave):
  1. Load `Settings`
  2. `setup_observability(settings)`
  3. Load `AgentRegistry`
  4. Initialize `PMAdapter` and `VCSAdapter` from `Settings.pm_adapter` / `Settings.vcs_adapter`
  5. Initialize `FileIndexService` and `CodeDiscoveryAgent`; run the `agent.md`-exists preflight check described above (no scan)
  6. `StateStore.load_or_init(project_id)` → `ProjectState`
  7. `PMAdapter.get_project(project_id)` → `Project`
  8. `PMAdapter.get_tasks(project_id)` → `list[Task]`
  9. `since = state.last_run_at or state.created_at`
  10. `new_comments = PMAdapter.read_new_comments(project_id, since=since)`
  11. Update `state.last_run_at = datetime.utcnow()` and save
  12. Build `OrchestratorInput` from project + tasks + new_comments + local_state verdicts (`TaskViewBuilder`)
  13. Call `Orchestrator.run_loop` → `OrchestratorOutput`
  14. If `done=True`: `VCSAdapter.create_project_pr(project_branch → main)`; print summary; exit
  15. Create new tasks in list order: for each `NewTask`, call `PMAdapter.create_task` → receive real task ID; register it as `"new:{index}"` in a local resolution map. Once all tasks are created, call `PMAdapter.set_dependency` for each task, resolving any `"new:N"` refs in `depends_on` to their real task IDs via the map before the call.
  16. Re-read tasks via `PMAdapter.get_tasks` (includes newly created ones) → `TaskScheduler.start` → runs all ready tasks to completion
  17. Print wave summary: N complete, M needs-human-review, K blocked
  18. Exit (user re-runs after addressing needs-human-review tasks)
- `--dry-run` flag: skip all write operations (PM adapter, VCS adapter, disk edits); log what would have been done
- `Settings.dry_run: bool = False` — set from `--dry-run` flag at startup; threaded through to executor and adapters
- Stream task status lines to terminal as tasks complete

**Success Criteria**
- [ ] `haive run --project 7` starts without crashing (graceful error if project doesn't exist)
- [ ] `haive run --project 7 --dry-run` runs full logic without writing files or calling adapter write methods
- [ ] Startup errors (bad config, invalid registry, schema version mismatch) exit with a clear message and non-zero status code
- [ ] Task completions (and `needs-human-review` events) print to terminal in real time
- [ ] On `done=True`: project branch → main PR is created and URL is printed
- [ ] `haive run` exits with a clear error if no `agent.md` files exist at the repo root, instructing the user to run `haive index` — it does not generate them itself
- [ ] `haive --help` documents `--project`, `--dry-run`, `haive index`, and `haive index --validate`

**Deferred:** No additional CLI subcommands.

---

## Phase 11: Integration Test

### Step 24 — End-to-End Integration Test

**Goal:** Verify the full system works on a real (but simple) project against a test repository.

**Scope**
- `tests/integration/` directory
- A dedicated test GitHub repository (or a fixture branch on the haive repo itself)
- Test project: "Add a docstring to the `greet` function in `hello.py`" — simplest possible single-task project
- `tests/integration/test_e2e.py`:
  - Create a test project and GitHub Issue programmatically via `GitHubPMAdapter` and `GitHubVCSAdapter`
  - Run `haive run --project <id>` as a subprocess
  - Assert:
    - The local state file is created at `~/.haive/state/owner/repo/project_{id}.json`
    - The state file contains one `TaskExecutionRecord` with `verdict.passed=True`
    - The task in the project has status `complete` in the PM tool
    - A task PR was created and merged into the project branch
    - A project → main PR was created (done=True triggered)
  - Clean up: delete the test project, Issues, PRs, and branches after the test
- Document in `tests/integration/README.md` what environment variables, GitHub token permissions, and repo settings (auto-merge enabled) are required
- Mark integration tests with `@pytest.mark.integration` and exclude from default `pytest` run

**Success Criteria**
- [ ] `pytest -m integration` succeeds end-to-end (requires real GitHub token and API keys in env)
- [ ] The single-task project results in a `passed` verdict and a merged task PR with no human intervention
- [ ] The local state file reflects the completed `TaskExecutionRecord`
- [ ] The project → main PR is created when done=True
- [ ] The test cleans up after itself (project, Issues, PRs, branches deleted)
- [ ] `pytest` (without `-m integration`) continues to pass unit tests only

**Deferred:** Multi-task projects, parallel executor tests, and eval runs are follow-on work.

---

## Dependency Order Summary

```
Steps 1-9 (Foundation)
    ├── Step 10 (Orchestrator) ← needs Steps 5,7,8,9; independent of Discovery chain
    │
    ├── Step 11 (agent.md Spec + Validator)
    │     └── Step 12 (FileIndexService: generate_all / haive index)
    │           └── Step 13 (Code Discovery Agent)
    │                 └── Step 14 (FileIndexService: load_sections)
    │                       └── Step 15 (FileIndexService: update_after_task)
    │
    └── Steps 16-20 (Execution Pipeline) ← needs Steps 9,14,15 + Steps 6,7,8,17,18,19
          └── Step 21 (Task Scheduler) ← needs Steps 7,20
                └── Step 22 (Observability) ← wraps Steps 20,21
                      └── Step 23 (CLI) ← wires Steps 10,21,22
                            └── Step 24 (E2E Test)
```

Steps 10, 11–15, and 16–20 are independent of each other after Step 9 and can be developed in parallel.

---

## Notes

- **Model calls in tests:** All LLM calls in unit tests use mocks. Only the integration test (Step 24) makes real calls.
- **Agent prompt quality:** Step 18 establishes structure. Prompts are expected to be iterated on once the system is running end-to-end.
- **Observability first:** The OTel setup (Step 22) should be the first thing called in the CLI — even before the registry loads — so that startup failures are traced.
- **File locking:** Implemented in Step 7 and relied upon by Step 21. Do not skip the concurrent-write test.
- **`--dry-run`:** Introduced in Step 23 and used for local development iteration without GitHub side effects.
