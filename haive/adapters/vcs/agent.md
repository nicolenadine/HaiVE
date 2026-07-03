## Files

__init__.py — Package initialization file for VCS adapters
base.py — VCSAdapter protocol defining version control system interface
  VCSAdapter (class) — 4-12 — Protocol for VCS operations including branch, PR, and merge management
github.py — GitHub implementation of VCS adapter using PyGithub and GraphQL
  GitHubVCSAdapter (class) — 12-98 — Concrete GitHub adapter for branch creation, PR management, and automated merging
