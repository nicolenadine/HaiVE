## Files

__init__.py — Package initialization for project management adapters
base.py — PMAdapter protocol defining interface for project management integrations
  PMAdapter (class) — 8-16 — Protocol specifying read/write methods for task management
github.py — GitHub Projects v2 adapter implementing project and task operations
  GitHubPMAdapter (class) — 60-418 — Full-featured adapter syncing tasks with GitHub issues and projects
  _GitHubIssue (class) — 37-49 — Pydantic model representing a GitHub issue with haive custom fields
  _GitHubMilestone (class) — 52-57 — Pydantic model representing a GitHub milestone
