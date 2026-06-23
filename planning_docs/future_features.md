# Haive — Future Features (Post-V1)

Features deferred until the core v1 system is complete and working end-to-end.

---

## CLI

### `haive milestone list`
List all open milestones on the configured repo with their numbers and titles,
so the user can identify which milestone to pass to `haive run --project <N>`
without having to open GitHub.

Example output:
```
  1   Add authentication module
* 2   API integration layer        ← active (last used)
  3   Documentation pass
```

---

### `haive project setup` — Project Setup Wizard
Interactive wizard that automates the one-time GitHub setup required before
running haive on a new repo. Walks the user through:

1. Creating a GitHub Projects v2 board (or linking an existing one)
2. Adding all required custom fields with the correct types and option values:
   - `haive_agent_role` (single select — all 10 `AgentRole` values)
   - `haive_complexity` (single select — `low`, `medium`, `high`)
   - `haive_lineage_depth` (number)
   - `haive_recovery_for` (text)
   - `haive_acceptance_criteria` (text)
3. Configuring the Status field with haive's expected values
4. Writing `GITHUB_PROJECT_ID` to the active haive config automatically

Goal: eliminate the current manual setup step entirely so a new user can go
from zero to a configured project board in a single command.

---

## GitHub Native Issue Relationships

`haive_depends_on` is currently a text custom field (comma-separated issue numbers) because
GitHub's `issueRelationships` GraphQL field (`IS_BLOCKED_BY`) is not available on personal
accounts — it requires a higher GitHub plan.

If/when that API becomes broadly available, replace the `haive_depends_on` text field with
native BLOCKS/IS_BLOCKED_BY relationships. This would:
- Remove `haive_depends_on` as a required custom field (back to 5)
- Restore `_get_blocked_by()` in `GitHubPMAdapter`
- Make dependency data visible natively in the GitHub UI without a custom field
