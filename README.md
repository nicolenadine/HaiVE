# Haive

Haive is a multi-provider AI agent harness that coordinates specialized sub-agents to complete software development tasks. It uses GitHub Projects and Issues as its coordination layer, routes work to the right model tier based on task complexity, and manages a full review-and-retry loop before auto-merging per-task PRs into a project branch.

## Quick Start

Before running haive, create and configure a named config:

```
haive config create myproject
haive config set GITHUB_TOKEN <your-token>
haive config set GITHUB_REPO owner/repo
haive config set GITHUB_PROJECT_ID <project-id>
```

Then run haive against a GitHub Project:

```
haive run
```

`GITHUB_PROJECT_ID` is the human-readable project number shown in the GitHub Projects URL (e.g., `github.com/orgs/myorg/projects/7` → `7`). You can override it for a one-off run without changing your config:

```
haive run --project <id>
```

Re-run after addressing any `needs-human-review` issues to continue the next wave of tasks.

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
