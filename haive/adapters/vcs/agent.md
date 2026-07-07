## Files

__init__.py — Package initialization for VCS adapters
base.py — VCSAdapter protocol defining version control interface
  VCSAdapter (class) — 4-15 — Protocol for VCS operations including branch, PR, and merge management
github.py — GitHub implementation of VCS adapter using PyGithub and GraphQL
  GitHubVCSAdapter (class) — 14-164 — Concrete GitHub adapter for branch management, PR creation, and merging
  _graphql (method) — 28-42 — Execute GraphQL queries against GitHub API with error handling
