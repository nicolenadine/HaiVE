## Files

__init__.py — Package initialization for PM adapters
base.py — PMAdapter protocol defining project management interface
  PMAdapter (class) — 8-16 — Protocol for reading and writing project/task data
github.py — GitHub Projects adapter implementing PMAdapter for issue tracking
  GitHubPMAdapter (class) — 60-410 — Adapter for GitHub Projects V2 custom field mapping and mutation
  _GitHubIssue (class) — 37-49 — Pydantic model for GitHub issue field extraction
  _GitHubMilestone (class) — 52-57 — Pydantic model for GitHub milestone representation
