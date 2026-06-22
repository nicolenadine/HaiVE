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
