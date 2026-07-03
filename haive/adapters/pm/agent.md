## Files

__init__.py — Package initialization
base.py — PMAdapter protocol defining project management interface
  PMAdapter (class) — 5-13 — Protocol for project management adapters with read and write operations
github.py — GitHub project management adapter implementation
  GitHubPMAdapter (class) — 56-452 — Adapter for GitHub Projects V2 with issue tracking and custom fields
  _graphql (method) — 67-80 — Execute GraphQL queries against GitHub API with error handling
  _resolve_project_node_id (method) — 82-107 — Resolve and cache GitHub Project V2 node ID
  _validate_custom_fields (method) — 109-146 — Verify required haive custom fields exist on project
  _extract_field_values (method) — 148-160 — Extract haive and status field values from GitHub field nodes
  _map_issue_to_task (method) — 162-180 — Convert GitHub issue with custom fields to Task model
  get_project (method) — 298-305 — Retrieve project metadata from milestone
  get_tasks (method) — 307-341 — Fetch all tasks assigned to a milestone with status and metadata
  read_new_comments (method) — 343-365 — Read comments added to tasks since a given datetime
  create_task (method) — 401-437 — Create new GitHub issue and add to project with haive fields
  set_dependency (method) — 439-442 — Update task dependency field
  update_status (method) — 444-449 — Update task status in project
  add_comment (method) — 451-452 — Add comment to GitHub issue
