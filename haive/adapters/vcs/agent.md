## Files

base.py — VCSAdapter protocol defining version control operations interface
  VCSAdapter (class) — 4-17 — Protocol specifying VCS operations for branch and PR management
github.py — GitHub adapter implementing VCS operations via PyGithub and git CLI
  GitHubVCSAdapter (class) — 14-196 — Concrete GitHub implementation handling branches, PRs, and commits
  _graphql (method) — 28-42 — Executes GitHub GraphQL queries with authentication
  create_branch (method) — 44-66 — Creates a remote branch and local checkout from base branch
  push_commits (method) — 68-81 — Stages, commits, and pushes specified files to branch
  checkout_branch (method) — 83-98 — Switches to branch and syncs with remote origin
  create_pr (method) — 100-110 — Creates pull request from head to base branch
  merge_pr (method) — 112-144 — Merges PR immediately or enables auto-merge if pending checks exist
  find_pr_for_branch (method) — 158-164 — Finds PR number and merge status for given head branch
  ensure_branch (method) — 169-189 — Creates or syncs branch, preserving history on existing branches
  branch_has_new_commits (method) — 191-196 — Checks if head branch has commits ahead of base
