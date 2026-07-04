## Files

base.py — VCSAdapter protocol defining common version control operations interface
  VCSAdapter (class) — 4-10 — Protocol for VCS implementations with branch, PR, and commit methods
github.py — GitHub-specific VCS adapter implementation using PyGithub and GraphQL
  GitHubVCSAdapter (class) — 14-92 — Concrete adapter for GitHub PR and branch operations
  _graphql (method) — 28-42 — Executes GitHub GraphQL queries with authorization
__init__.py — Package exports for VCS adapters
