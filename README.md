# Haive

Haive is a multi-provider AI agent harness that coordinates specialized sub-agents to complete software development tasks. It uses GitHub Projects and Issues as its coordination layer, routes work to the right model tier based on task complexity, and manages a full review-and-retry loop before auto-merging per-task PRs into a project branch.

## Quick Start

Before running haive, create and configure a named config:

```
haive config create myproject
haive config set GITHUB_TOKEN <your-token>
haive config set GITHUB_REPO owner/repo
```

Then set up haive's GitHub Project board — this creates (or reuses) a Projects v2 board, adds the custom fields haive needs, and writes `GITHUB_PROJECT_ID` into your active config automatically:

```
haive project setup
```

Generate the code index haive uses for context retrieval:

```
haive index
```

Then run haive against a milestone on that project (a milestone is a real GitHub Milestone — see "How it works" below):

```
haive run --project <milestone-number>
```

Re-run after addressing any `needs-human-review` issues to continue the next wave of tasks.

### Required token permissions

`GITHUB_TOKEN` needs a classic personal access token with the `repo` and `project` scopes. If the repository is owned by an organization, the token may also need `read:org`, and the organization may need to approve the PAT before it can access org resources.

### Manual board setup

If you'd rather configure the board by hand, or already have one you want to reuse across repos, skip `haive project setup` and set `GITHUB_PROJECT_ID` directly:

```
haive config set GITHUB_PROJECT_ID <project-id>
```

`GITHUB_PROJECT_ID` is the human-readable project number shown in the GitHub Projects URL (e.g., `github.com/orgs/myorg/projects/7` → `7`).

A manually-configured board must have these custom fields, with these exact names and types:

| Field | Type | Options |
|---|---|---|
| `haive_agent_role` | single select | `scaffold_agent`, `implementation_agent`, `code_editor_agent`, `refactoring_agent`, `api_integration_agent`, `database_agent`, `test_generator_agent`, `code_reviewer_agent`, `security_reviewer_agent`, `documentation_writer_agent` |
| `haive_complexity` | single select | `low`, `medium`, `high` |
| `haive_depends_on` | text | — |
| `haive_lineage_depth` | number | — |
| `haive_recovery_for` | text | — |
| `haive_acceptance_criteria` | text | — |

The board's built-in `Status` field also needs its options set to: `pending`, `in_progress`, `complete`, `needs_human_review`, `awaiting_merge`, `blocked`, `skipped`.

## How it works

A **milestone** is a real GitHub Milestone — its title and description are the spec haive plans work from. Each milestone gets its own dedicated git branch (`haive/project-<id>`), created the first time you run it and reused on every subsequent invocation.

A single `haive run` invocation loops across **waves**, up to `max_waves_per_run` (default 2):

1. **Plan** — if there are no pending tasks, the orchestrator reads the milestone spec, the current task board, a map of the codebase, and any new human comments, then either creates new tasks or signals the milestone is done.
2. **Execute** — each task runs through discovery (find relevant code), generation (a model writes the change), and review (a separate model checks it against the task's acceptance criteria). Failures retry with feedback and escalate through model tiers (low → medium → high) before falling back to `needs_human_review`.
3. **Merge** — a passing task's branch is pushed, a PR is opened against the milestone branch, and — unless `--no-merge` — merged automatically. Only the *milestone's* final PR (branch → `main`, created once the orchestrator signals done) is never auto-merged; that one is always left for human review.

Re-running `haive run` against the same milestone picks up where it left off — reconciling any tasks that were manually merged since the last run, and continuing planning from the current task board state.

## Commands

| Command | Purpose |
|---|---|
| `haive config create/use/set/show/list/edit/delete` | Manage named configs (`~/.haive/configs/<name>.env`). Only one config is "active" at a time. |
| `haive project setup` | Create or configure a Haive-compatible GitHub Project v2 board; writes `GITHUB_PROJECT_ID` back to the active config. |
| `haive index [--validate]` | Generate (or validate) the per-directory `agent.md` index task agents use to navigate the repo. Required before `haive run`. |
| `haive run [--project N] [--dry-run] [--no-merge] [--quiet]` | Run the harness against a milestone. See "How it works" above and `haive run --help` for all flags. |
| `haive prune-branches [--yes]` | List `haive/task-*` branches whose PRs have been merged, and delete them after confirmation. |
| `haive discover <description>` | Standalone: preview what code context the discovery agent would surface for a task description, without running anything. |
| `haive load <description>` | Standalone: preview the actual loaded source content for a task description (discover + load), as a task would see it. |

Every command supports `--help` for the full list of options.

## Configuration reference

Set via `haive config set KEY VALUE` in the active config. Required keys are marked; everything else has a sensible default.

| Key | Required | Default | Purpose |
|---|---|---|---|
| `GITHUB_TOKEN` | yes | — | GitHub token; see "Required token permissions" above. |
| `GITHUB_REPO` | yes | — | `owner/repo`. |
| `GITHUB_PROJECT_ID` | yes | — | Projects v2 board number. Set automatically by `haive project setup`. |
| `GITHUB_MILESTONE_ID` | no | — | Default milestone for `haive run` when `--project` isn't passed. |
| `ANTHROPIC_API_KEY` | one of these two | — | Needed if any configured tier/reviewer model uses `anthropic/...`. |
| `OPENAI_API_KEY` | one of these two | — | Needed if any configured tier/reviewer model uses `openai/...`. |
| `OLLAMA_API_BASE` | no | `http://localhost:11434` | Base URL for local Ollama models, if used. |
| `MAX_WAVES_PER_RUN` | no | `2` | Caps how many plan/execute waves one `haive run` invocation will loop through automatically. |
| `MAX_RECOVERY_DEPTH` | no | `3` | Caps how many times the orchestrator can chain recovery tasks for the same failure lineage before escalating to a human. |
| `MAX_EXECUTORS` | no | `4` | Max tasks executed concurrently within a wave (only independent tasks — dependency order is always respected). |
| `OBSERVABILITY_ENABLED` | no | `false` | Enables OpenTelemetry tracing (with LiteLLM auto-instrumentation) for each run. |
| `PHOENIX_OTLP_ENDPOINT` | no | `http://localhost:6006/v1/traces` | Where OTel traces are exported when observability is enabled. |

Model tiers (`TIER_LOW_MODELS`, `TIER_MEDIUM_MODELS`, `TIER_HIGH_MODELS`, `REVIEWER_MODELS`) and their attempt counts/context budgets have working defaults spanning Anthropic and OpenAI models; override them the same way if you want a different mix or a single provider. Each value is a comma-separated list of LiteLLM-style model identifiers (e.g. `anthropic/claude-sonnet-4-6,openai/gpt-4o`) — the first is primary, the rest are fallbacks.

Per-agent-role behavior (system prompts, output schemas, max tokens, retry limits) is configured separately in `agents.yaml` at the repo root, not through `haive config`.

## Repository requirements

Haive scans your repository to build a structural code map used for context retrieval. The scanner respects your `.gitignore` — directories and files listed there are excluded from indexing. **A complete `.gitignore` is required for correct behaviour.**

If `.gitignore` is missing or incomplete, the scanner will walk everything it can reach — including installed packages in `.venv`, compiled artifacts in `dist/`, or generated files in `build/`. These files dominate the ranking and push your actual project code out of the context window entirely.

At minimum, your `.gitignore` should exclude:

```
.venv/
__pycache__/
dist/
build/
*.egg-info/
```

Add any other directories that are not part of your project's source (test fixtures, generated code, vendor directories, etc.). The quality of haive's context retrieval is directly proportional to the accuracy of your `.gitignore`.
