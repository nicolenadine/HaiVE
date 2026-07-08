## Files

__init__.py — Package initialization for project management adapters
base.py — PMAdapter protocol defining interface for project management tools
  PMAdapter (class) — 8-17 — Protocol interface for reading/writing tasks and milestones
board_setup.py — GitHub Project v2 board creation and configuration utilities
  BoardSetupResult (class) — 65-73 — Result summary of board setup operation
  setup_board (function) — 252-273 — Creates or reuses a Haive-compatible GitHub Project v2 board
github.py — GitHub integration adapter implementing PMAdapter protocol
  GitHubPMAdapter (class) — 73-439 — Reads/writes tasks and milestones via GitHub API and Projects v2
