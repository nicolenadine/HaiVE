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

### add nice formatting and colors to cli interface. 

### add a quick setup wizzard so that all required parameters don't have to be manually set one-by-one using `haive config set` 
`haive congfig set` is useful for changing one parameter but setting them all is tedious 

### update --help to reflect all functionality of cli 

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

## Token-Efficient Agent Output (Partial File Edits)

Agent output schemas currently require returning complete file content for every file edited
(`CodeEditorOutput.edits[].content`). This is reliable but wasteful when only a few lines change.

**Preferred approach when revisiting:** hybrid schema — agent writes `content` (full file) for
large changes or new files, and `changes: [{search, replace}]` for small targeted edits. The
agent decides based on change scope; the executor handles both paths.

**Why deferred:** search-and-replace has a serious uniqueness risk in an autonomous context —
a false match silently corrupts a file with no human to catch it. Full-file rewrites are
reliable and the token cost (output tokens are ~5x cheaper than input) is manageable at current
scale. Revisit once the system is running end-to-end and token cost is measurable.

**Scope of change when ready:** `haive/models/agent_output.py` (`FileEdit` model), all editing
agent prompts (`prompts/`), and the file-writing logic in the Task Executor.

---

## Reviewer & Orchestrator Context Awareness

### Full repo navigation for the Reviewer Agent
`ReviewAgent` can currently only request a file it can already name from something visible
in front of it (an import statement, a call site) — it cannot browse the repo from scratch.
If reviews keep missing gaps because the relevant file was never referenced anywhere in view,
give it the same `read_agent_md`/`list_subdirectories` navigation tools `CodeDiscoveryAgent`
uses, so it can search rather than only confirm a lead it already has. Deferred to keep the
initial on-demand file-read change small; revisit after seeing whether path-only requests move
the needle in practice.

### Raise `max_waves_per_run` once autonomous recovery proves reliable
`haive run` currently caps automatic wave looping at 2 per invocation — deliberately
conservative while the infeasible-verdict auto-recovery and orchestrator repo-map changes are
new and unproven. Raise this once a track record of correct automatic recoveries builds up
confidence that a stalled or misbehaving loop won't silently burn many waves of tokens.

### Symbol line-range correction for non-Python languages
`haive/discovery/symbol_line_corrector.py` (see `build_plan.md`'s H1) only corrects
Python files, using the stdlib `ast` module for exact, no-guessing line ranges. Other
languages `SOURCE_EXTENSIONS` supports (JS/TS, Go, Java, Ruby, Rust, C/C++, C#, Swift)
still rely on the LLM's estimate, same as before this fix — not worse, just not improved.
Extending this would need either a per-language parser (tree-sitter — a new dependency,
and one that would need real non-Python source in this repo to validate against) or a
simpler regex-plus-brace-depth-counting heuristic per language. Deferred until haive is
actually run against a non-Python project, so the approach can be validated against real
code rather than built speculatively.

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
