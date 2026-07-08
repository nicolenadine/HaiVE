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

Then run haive against a milestone on that project:

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
