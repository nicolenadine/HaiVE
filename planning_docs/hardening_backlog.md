# Haive — Hardening Backlog

Issues identified during review that are deferred from their respective implementation steps.
Each item describes the problem, why it was deferred, and what the fix should look like.

Address these before or during the v1 integration testing phase, not necessarily in order.

---

## 1. `push_commits()` cwd and path safety

**Problem:** `GitHubVCSAdapter.push_commits()` runs `git add/commit/push` without a `cwd`
argument, so it operates on whatever directory the process is in. It also does not validate
that `changed_files` are relative paths inside the repo root. An executor bug could stage
files from outside the intended directory.

**Deferred because:** Setting `cwd` and checking out the right task branch is the executor's
responsibility (Step 21). The adapter cannot know the repo root at this layer.

**Fix when building the executor:**
- Pass `repo_root: str` to `push_commits()` (or inject it at construction)
- Run all subprocess calls with `cwd=repo_root`
- Validate that every path in `changed_files` is relative and does not escape via `../`
- Reject `changed_files=[]` with a clear error

---

## 2. Field value pagination — 20-field-value limit per board item

**Problem:** `_fetch_project_items()` fetches `fieldValues(first: 20)` per item. A project
board item with more than 20 field values would silently drop values, causing required
haive_* fields to fall back to defaults (e.g. `status` defaults to `"pending"`, `complexity`
to `"low"`).

**Deferred because:** 20 is well above the current field count (8 including Status), so this
is not a live risk yet.

**Fix:** Increase the limit to something generous (e.g. 50), or paginate field values per
item. Also add a loud failure if a required field value is absent after parsing rather than
silently defaulting.

---

## 3. Config file permissions

**Problem:** `ConfigManager._bootstrap_default()` and `ConfigManager.create()` use
`Path.touch()` without setting permissions. On systems with a permissive umask, the resulting
`.env` files (which contain `GITHUB_TOKEN`, `OPENAI_API_KEY`, etc.) may be readable by other
local users.

**Deferred because:** It requires OS-level permission handling and is low risk in single-user
dev environments.

**Fix:**
- After creating `~/.haive/` and subdirs, set them to `0o700`
- After creating any `.env` config file, set it to `0o600`
- Optionally warn at startup if an existing config file has permissions looser than `0o600`

---

## 4. Git error messages may leak secrets

**Problem:** `push_commits()` surfaces raw `stdout`/`stderr` from failed git commands in the
raised `RuntimeError`. Git can echo credential-helper output or token-bearing remote URLs
in error messages.

**Deferred because:** No CI is running git commands yet; the risk is low during local dev.

**Fix:** Before surfacing subprocess output in an exception, redact anything that looks like a
token (e.g. `ghp_[A-Za-z0-9]+`) or a URL containing `@`. A simple regex pass on the stderr
string is sufficient.

---

## 5. `haive run` preflight does not validate settings

**Problem:** `_preflight_checks()` in `haive/cli.py` only checks that `git` is on PATH and
that an active config file exists. It does not call `load_settings()`, so a missing or empty
config passes preflight. The error surface only when the adapter tries to use a `None` token.

**Deferred because:** `load_settings()` is wired up in Step 23 (full CLI harness).

**Fix:** After Step 23, have `_preflight_checks()` call `load_settings()` and surface a
human-readable error that names the missing fields and the config file path on failure.

---

## 6. Partial task creation leaves broken GitHub issues

**Problem:** `create_task()` creates the GitHub issue, adds it to the board, then sets each
of the 6 haive_* fields one by one. If any field update fails (network, missing option ID,
etc.), an issue is left on the board with missing or default field values.

**Deferred because:** Adding compensation logic (detect failure, close/comment the issue as
malformed) is non-trivial and the failure mode is rare during normal operation.

**Fix:**
- Wrap the field-update loop in a try/except
- On failure: post a comment on the issue noting the creation failure, then close it
- Consider batching field updates into a single GraphQL operation if GitHub exposes that

---

## 7. Startup option validation for single-select fields

**Problem:** `_validate_custom_fields()` caches option IDs for `Status`, `haive_agent_role`,
and `haive_complexity`, but does not verify that every expected value (`TaskStatus`,
`AgentRole`, `Complexity` enum members) has a corresponding option. A `KeyError` would occur
at the point of task creation or status update — after a GitHub issue has already been created
(see item 6).

**Deferred because:** Combined fix with item 6 is more tractable; this alone just surfaces
the error earlier.

**Fix:** After `_validate_custom_fields()` populates the option maps, verify that every enum
value has an entry. Raise a `RuntimeError` at startup listing any missing options.

---

## 8. Boundary models should forbid extra fields

**Problem:** Most Pydantic models use the default `extra="ignore"` behaviour. For boundary
schemas (task, state, verdict, agent output) this can silently hide bugs where an LLM or
external caller passes unexpected fields.

**Deferred because:** Requires touching many models and can break tests that pass extra fields.

**Fix:** Add `model_config = ConfigDict(extra="forbid")` to:
- `Task`, `Project`, `TaskComment`
- `ProjectState`, `TaskExecutionRecord`, `AttemptLogEntry`, `VerdictSummary`
- `ReviewVerdict`
- All agent output schemas

---

## 9. `ReviewVerdict` missing invariant validators

**Problem:** `ReviewVerdict` allows `uncertain=True` and `passed=True` simultaneously, which
the data model says is a logic error. It also allows an empty `reason` string.

**Deferred because:** The executor and output validator (Steps 18–20) are the enforcement
point; adding validators to the model is a secondary defence.

**Fix:** Add `@model_validator(mode="after")` to `ReviewVerdict`:
- `uncertain=True` must imply `passed=False`
- `reason.strip()` must be non-empty

---

## 10. Core model validators

**Problem:** Several fields in task/state models accept logically invalid values:
- `lineage_depth` can be negative
- `depends_on` can contain duplicates or the task's own ID
- `TokenUsage.total_tokens` can disagree with `prompt_tokens + completion_tokens`
- `TaskExecutionRecord.total_attempts` can be negative

**Deferred because:** These are internal invariants that only break via bugs in haive itself,
not external input. They are low risk until the executor is wired up.

**Fix:** Add `@field_validator` or `@model_validator` entries for the above on the relevant
models in `haive/models/task.py` and `haive/models/state.py`.
