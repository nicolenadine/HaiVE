## Files

__init__.py — Package initialization for project management adapters
base.py — PMAdapter protocol defining interface for project management tools
  PMAdapter (class) — 8-19 — Protocol interface for reading/writing tasks and milestones
board_setup.py — GitHub Project v2 board creation and configuration utilities
  BoardSetupResult (class) — 65-73 — Result summary of board setup operation
  setup_board (function) — 252-273 — Creates or reuses a Haive-compatible GitHub Project v2 board
github.py — GitHub integration adapter implementing PMAdapter protocol
  _parse_checkpoint (function) — 33-40 — Parses #Checkpoint marker from milestone description
  _bounded_text (function) — 26-30 — Truncates text to GitHub field limit with marker
  _GitHubIssue (class) — 65-77 — Pydantic model for GitHub issue field values
  _GitHubMilestone (class) — 80-85 — Pydantic model for GitHub milestone metadata
  GitHubPMAdapter (class) — 88-502 — Reads/writes tasks and milestones via GitHub API and Projects v2
