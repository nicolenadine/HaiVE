# Haive — Communication Protocol

## Purpose

Defines what flows between each component: the format of every handoff, the fields each receiver needs, and what each sender must never include. Precise schemas are deferred to the Data and State Model doc — this document defines structure and rules.

---

## Core Communication Principles

- **Structured, not prose.** Every inter-component handoff is a typed, validated object. No free-form text passed between system components (only within agent prompts and outputs).
- **Minimal.** Each receiver gets only what it needs. No component broadcasts full context to all downstream components.
- **Agents receive data, they do not call services.** The Task Executor is responsible for fetching and passing data to the Context Assembler and Review Agent. Those components format and judge; they do not reach out.
- **Git is the source of truth for file changes.** After any agent edit, file changes are verified via `git diff --name-only` — not from agent self-reporting alone.
- **No reasoning traces cross component boundaries.** Agents pass decisions, outputs, and verdicts — not their chain of thought.

---

## Communication Flows

### 0. GitHub Service → Orchestrator (Milestone + Issue statuses + comments)

The orchestrator's objective is a GitHub Milestone — not a free-text string. At startup, the GitHub Service fetches the Milestone and all Issues in it. On every subsequent run, the GitHub Service also fetches new comments on any Issues since `last_run_at`, so the orchestrator can detect human guidance posted on `needs-human-review` Issues.

**Milestone object (at startup):**
```json
{
  "milestone_id": 7,
  "title": "Email validation for user registration",
  "description": "## What\nAdd RFC 5322 validation to UserRegistrationHandler.post.\n\n## Acceptance Criteria\n- Returns HTTP 422 with descriptive error on invalid input\n- Does not break existing registration flow",
  "state": "open"
}
```

**Issues (each run — all Issues in the Milestone):**
```json
[
  {
    "issue_number": 101,
    "title": "Add email format validation",
    "body": "...",
    "status": "complete",
    "blocked_by": [],
    "verdict": { "passed": true, "reason": "All acceptance criteria met." }
  },
  {
    "issue_number": 102,
    "title": "Update registration tests for new validation contract",
    "body": "...",
    "status": "needs-human-review",
    "blocked_by": [101],
    "verdict": { "passed": false, "reason": "Breaks test_valid_registration on line 88." }
  }
]
```

Note: `verdict` on each Issue is read from the **local state file** by the CLI and merged into the Issue view before passing to the orchestrator. GitHub Issues hold status; local state holds the verdict detail.

**New comments (each run, on Issues with status needs-human-review or any recent activity):**
```json
{
  "new_issue_comments": [
    {
      "issue_number": 102,
      "author": "human",
      "body": "The test on line 88 is testing the old behavior intentionally — update the test to match the new validation contract.",
      "created_at": "<timestamp>"
    }
  ]
}
```

The orchestrator uses new human comments to inform its next decision: create a recovery task incorporating the guidance, or leave the Issue in `needs-human-review` if more context is needed.

---

### 1. Orchestrator → GitHub Issues

The orchestrator creates one or more GitHub Issues per loop. Each Issue represents a task. The GitHub Service translates `OrchestratorOutput.new_tasks` into API calls.

**Issue creation request (one per new task):**
```json
{
  "title": "Add email format validation to UserRegistrationHandler.post",
  "body": "## Task\nAdd RFC 5322 validation to UserRegistrationHandler.post\n\n## Acceptance Criteria\n- Validates email matches RFC 5322 format\n- Returns HTTP 422 with descriptive error on invalid input\n- Does not break existing valid registration flow\n\n---\n_lineage_depth: 0 | recovery_for: null_",
  "milestone_id": 7,
  "agent_role": "code_editor",
  "complexity": "medium",
  "blocked_by": [99, 100]
}
```

After creation, the GitHub Service:
1. Creates the Issue (GitHub API)
2. Sets the `blocked by` relationship on the Issue to the referenced issue numbers (GitHub native dependency)
3. Sets the Issue's `status` Project field to `pending`
4. Records the new `issue_number → task_id` mapping in the local state file

`recovery_for` and `lineage_depth` are embedded in the Issue body (visible in the comment thread) so the orchestrator can read them back on the next run.

**What the orchestrator must NOT include in Issue bodies:** file paths, symbol names, implementation suggestions, model preferences, prior agent outputs.

---

### 2. GitHub Issues → Task Scheduler

The Task Scheduler reads the Milestone's Issue list from the GitHub Project on each scheduling cycle. It reads only the fields needed for dependency evaluation:

```json
{
  "issue_number": 103,
  "blocked_by": [99, 100],
  "status": "pending"
}
```

The Scheduler does not read Issue bodies, acceptance criteria, or verdicts. It evaluates readiness purely from `status` and the native `blocked_by` graph.

**Task readiness rules:**
- `ready`: `status == pending` AND all `blocked_by` Issues have `status == complete`
- `waiting`: `status == pending` AND at least one `blocked_by` Issue has `status == in_progress`
- `blocked`: `status == pending` AND at least one `blocked_by` Issue has `status == needs-human-review`

---

### 3. Task Scheduler → Task Executor

The Scheduler spawns a Task Executor and passes the Issue number and the full task object (assembled from the GitHub Issue body + local state mapping). The executor needs the Issue content plus current attempt state.

```json
{
  "issue_number": 103,
  "title": "Add email format validation to UserRegistrationHandler.post",
  "description": "Add RFC 5322 validation to UserRegistrationHandler.post",
  "agent_role": "code_editor",
  "complexity": "medium",
  "blocked_by": [99, 100],
  "acceptance_criteria": ["..."],
  "milestone_branch": "haive/milestone-7",
  "current_tier": "medium",
  "attempt": 1,
  "feedback": null
}
```

`current_tier` and `attempt` are managed by the Task Executor's retry/escalation loop and updated in-memory — not written to GitHub or local state on every retry, only on task completion or retries exhausted.

---

### 4. Task Executor → RepoMapService (`get_context_pack`)

**Request:**
```json
{
  "task_description": "Add email format validation to UserRegistrationHandler.post",
  "acceptance_criteria": [...],
  "token_budget": 6000
}
```

**Response (context pack):**
```json
{
  "relevant_symbols": [
    {
      "qualified_name": "UserRegistrationHandler.post",
      "file": "src/routes/auth.py",
      "start_line": 42,
      "end_line": 67,
      "source": "    def post(self, request):\n        ..."
    }
  ],
  "relevant_files": [
    {
      "path": "src/routes/auth.py",
      "included_reason": "defines UserRegistrationHandler"
    }
  ],
  "broken_references": [
    {
      "file": "src/routes/auth.py",
      "symbol": "validate_email",
      "line": 51,
      "note": "referenced but definition not found"
    }
  ],
  "impacted_files": [
    "tests/test_registration.py",
    "src/middleware/validation.py"
  ],
  "token_estimate": 1840
}
```

The `token_budget` enforces context size before the prompt is assembled. The RepoMapService trims lower-ranked symbols if the budget would be exceeded. `broken_references` and `impacted_files` are included in the pack so the Context Assembler can surface them to both the sub-agent and the Review Agent without additional service calls.

---

### 5. Task Executor → Context Assembler

The Context Assembler receives the task object (from the GitHub Issue), the context pack, the Issue comment thread, dependency PR summaries, and any retry feedback. It does not call any services.

**Input to Context Assembler:**
```
task:               full task object (from GitHub Issue body)
context_pack:       RepoMapService response
issue_comments:     list of comments on this Issue (human guidance, prior executor comments)
dependency_outputs: { issue_number: { "summary": "..." }, ... }
feedback:           null | { "reason": "...", "suggestions": [...] }
agent_config:       { system_prompt: "...", output_schema: {...}, max_tokens: 4096 }
```

**Output (Messages list for LiteLLM):**
```json
[
  {
    "role": "system",
    "content": "<agent system prompt>"
  },
  {
    "role": "user",
    "content": "<assembled context: task + code snippets + broken refs + issue comments + dependency outputs + feedback>"
  }
]
```

**Assembly order within the user message:**
1. Task description and acceptance criteria (from Issue body)
2. Relevant code symbols and snippets (from context pack)
3. Broken references flagged by RepoMapService (if any)
4. Impacted files (awareness only — not included as full content)
5. Issue comment thread (human guidance, prior attempt context if needs-human-review)
6. Dependency task PR summaries (summarised, not full)
7. Reviewer feedback from prior attempt (if `attempt > 1`)

**What the Context Assembler excludes:** orchestrator reasoning, outputs of tasks not in `blocked_by`, full file contents when a symbol snippet is sufficient, run history beyond the current task.

---

### 6. LiteLLM → Output Validator

LiteLLM returns a raw string response. The Output Validator receives:

```
raw_response:  "<string returned by model>"
output_schema: "<Pydantic model for this agent role>"
agent_role:    "code_editor"
```

The Validator attempts JSON extraction from the raw string, then validates against the schema.

**On success:** passes the parsed, validated object downstream.
**On failure:** returns a structured error for the retry loop.

```json
{
  "valid": false,
  "error": "Missing required field: changed_files",
  "raw_response": "..."
}
```

---

### 7. Output Validator → Review Agent

On validation success, the Review Agent receives:

```
validated_output:    <parsed agent output object>
task:                full task object (description + acceptance_criteria)
context_pack:        the same context pack used for the agent call
                     (includes broken_references — Review Agent sees these as context)
attempt_number:      2
agent_role:          "code_editor"
guidelines:          "<contents of project guidelines file>"
```

The Review Agent does not call services. It receives everything it needs to make a quality judgment including broken reference information from the context pack.

---

### 8. Review Agent → Task Executor (verdict)

The Review Agent returns a structured verdict. The full verdict stays within the Task Executor's retry loop. Only a summary reaches the state file.

**Full verdict (Task Executor only):**
```json
{
  "passed": false,
  "reason": "Email validation is missing — the post method writes to the database without checking format.",
  "suggestions": [
    "Add a call to validate_email() before the db.save() call on line 58.",
    "Return HTTP 422 with {'error': 'invalid_email'} if validation fails."
  ]
}
```

**Summary verdict (written to state file, read by orchestrator):**
```json
{
  "passed": false,
  "reason": "Email validation is missing."
}
```

The orchestrator never sees `suggestions`. Those are consumed by the Task Executor to build the next retry's feedback context.

**`reason` quality requirement.** The `reason` field is the orchestrator's only window into why a task failed. It must be specific and actionable — not a generic label. The Review Agent's system prompt and output schema must enforce this.

| Unacceptable | Acceptable |
|---|---|
| "Failed to meet acceptance criteria." | "Email validation is missing — user input is written to the database without format checking." |
| "Output was incorrect." | "Returns HTTP 400 instead of 422 on invalid input, breaking the contract in acceptance criteria." |
| "Tests did not pass." | "Breaks existing test `test_valid_registration` on line 88 — the new validation rejects a previously valid email format." |

A vague `reason` leaves the orchestrator unable to make an intelligent next decision. The orchestrator's job when it reads a failed task is to create a follow-up task, adjust acceptance criteria, or decompose the work differently — none of which it can do without understanding what specifically went wrong.

---

### 9. Task Executor → Local State File (execution metadata)

On task completion or retries exhausted, the executor writes internal execution metadata to the local state file. This is the eval dataset — it is not used for scheduling decisions (GitHub Issues hold that state).

**Passed:**
```json
{
  "issue_number": 103,
  "verdict": {
    "passed": true,
    "reason": "All acceptance criteria met."
  },
  "model_used": "claude-sonnet-4-6",
  "tier_used": "medium",
  "total_attempts": 2,
  "agent_role": "code_editor",
  "prompt_version": "1.2.0",
  "changed_files": ["src/routes/auth.py"],
  "pr_number": 215,
  "completed_at": "<timestamp>",
  "token_usage": { "prompt_tokens": 2840, "completion_tokens": 612, "total_tokens": 3452 }
}
```

**Retries exhausted:**
```json
{
  "issue_number": 103,
  "verdict": {
    "passed": false,
    "reason": "Breaks existing test test_valid_registration on line 88 — new validation rejects a previously valid email format."
  },
  "attempt_log": [
    { "tier": "medium", "attempt": 1, "reason": "Email validation missing — input written to database without format check." },
    { "tier": "medium", "attempt": 2, "reason": "Validation added but returns HTTP 400 instead of 422." },
    { "tier": "high",   "attempt": 1, "reason": "Status code correct but breaks test_valid_registration on line 88." },
    { "tier": "high",   "attempt": 2, "reason": "Breaks test_valid_registration on line 88 — new validation rejects a previously valid email format." }
  ],
  "model_used": "claude-sonnet-4-6",
  "tier_used": "high",
  "total_attempts": 4,
  "agent_role": "code_editor",
  "prompt_version": "1.2.0",
  "changed_files": [],
  "pr_number": null,
  "completed_at": "<timestamp>",
  "token_usage": { "prompt_tokens": 9120, "completion_tokens": 1840, "total_tokens": 10960 }
}
```

The `attempt_log` records every attempt across all tiers — tier name, attempt number within that tier, and the reviewer's `reason` for that attempt. It does not include the reviewer's `suggestions` (those were consumed by the retry loop) or full reviewer prose.

The CLI merges `attempt_log` and `verdict` from local state into the orchestrator's Issue view on each run. The orchestrator uses the `attempt_log` to write a good recovery task:

| Pattern | Implication | Orchestrator response |
|---|---|---|
| Same reason every attempt | The task spec is wrong or missing key context | Rewrite the description and acceptance criteria |
| Reasons change with each attempt | Task is making progress but surfacing new edges | Decompose into smaller tasks with tighter scope |
| First few attempts wildly off, later ones close | Model needed the tier escalation to understand the problem | Recovery task may be well-defined as-is; try with clearer constraints |

`changed_files` is populated from `git diff --name-only` — not from agent self-reporting alone. On a failed task, `changed_files` is empty (no partial work is merged).

---

### 10. Task Executor → GitHub Service (on pass)

After the internal Review Agent passes, the executor performs the following GitHub operations in order:

**a) Create and merge the task PR:**
```json
{
  "head_branch": "haive/task-103",
  "base_branch": "haive/milestone-7",
  "title": "task-103: Add email format validation to UserRegistrationHandler.post",
  "body": "Closes #103\n\n## Changes\n- Added RFC 5322 validation in `src/routes/auth.py`\n- Returns HTTP 422 on invalid input"
}
```

**b) Add assumptions comment to the PR:**
```
🤖 haive executor note

**Assumptions made:**
- Treated the email format as described in RFC 5322 strictly (rejects quoted local parts)
- Did not modify the test file — the test on line 88 tests pre-validation behavior; marked as out-of-scope per task spec

**Open questions for human review:**
- Should + signs in the local part be allowed? Current implementation allows them.
```

**c) Auto-merge the PR:**
The executor calls `auto_merge_pr(pr_number)` immediately after creation. The task PR merges into the milestone branch without waiting for human review.

**d) Update Issue status:**
```json
{ "issue_number": 103, "status": "complete" }
```

On a failed verdict (retries exhausted), no PR is merged. The open task branch and PR (if one was partially created) are left as-is for context — the executor does not clean up.

---

### 11. Task Executor → RepoMapService (`update_files`)

After the task PR is merged, the executor triggers an incremental repo map refresh. This is the last action before shutdown:

```json
{
  "changed_files": ["src/routes/auth.py"]
}
```

---

### 12. GitHub Issues + Local State → Orchestrator (each run)

On each run, the CLI assembles the orchestrator's input by merging GitHub Issue statuses with verdict/attempt_log data from local state:

```
milestone: { "milestone_id": 7, "title": "...", "description": "..." }
issues: [
  {
    "issue_number": 101, "title": "Add email format validation",
    "status": "complete", "lineage_depth": 0, "blocked_by": [],
    "verdict": { "passed": true, "reason": "All criteria met." }
  },
  {
    "issue_number": 102, "title": "Update registration tests",
    "status": "needs-human-review", "lineage_depth": 0, "blocked_by": [101],
    "verdict": { "passed": false, "reason": "Breaks test_valid_registration on line 88." },
    "attempt_log": [
      { "tier": "medium", "attempt": 1, "reason": "Email validation missing." },
      { "tier": "medium", "attempt": 2, "reason": "Validation added but returns HTTP 400 instead of 422." },
      { "tier": "high",   "attempt": 1, "reason": "Status code correct but breaks test_valid_registration on line 88." },
      { "tier": "high",   "attempt": 2, "reason": "Breaks test_valid_registration on line 88 — rejects previously valid format." }
    ]
  },
  {
    "issue_number": 103, "title": "Recovery: update test contract for new validation",
    "status": "needs-human-review", "lineage_depth": 1, "recovery_for": 102, "blocked_by": [101],
    "verdict": { "passed": false, "reason": "Test updated but now rejects emails containing + signs." },
    "attempt_log": [
      { "tier": "medium", "attempt": 1, "reason": "Test updated but rejects + signs." },
      { "tier": "high",   "attempt": 1, "reason": "Test updated but rejects + signs." }
    ]
  },
  {
    "issue_number": 104, "title": "Add documentation for email validation",
    "status": "pending", "lineage_depth": 0, "blocked_by": [101]
  }
]
new_issue_comments: [
  {
    "issue_number": 103, "author": "human",
    "body": "The + sign issue is a known edge case in the validator library — use a different library or write a custom regex."
  }
]
agent_summary: "<compact one-line-per-agent summary from registry>"
```

The `attempt_log` (from local state) gives the orchestrator what it needs to write a meaningful recovery task. `lineage_depth` and `recovery_for` are embedded in the Issue body and surfaced here so the orchestrator can trace the lineage.

The orchestrator never receives: file contents, code snippets, review prose, token counts, model names, changed file lists, or the `suggestions` from any Review Agent verdict.

---

### 13. Retries Exhausted → GitHub Issue comment

When the executor exhausts all retries, it leaves a structured comment on the Issue summarizing every attempt. The orchestrator reads this comment on the next `haive run` and decides whether to create a recovery task incorporating human guidance.

**Issue comment posted by executor (automatically, on retries exhausted):**
```
🤖 haive executor: retries exhausted for this task

**Final failure reason:** Custom regex passes + signs but fails Unicode addresses (e.g. ü@example.com).

**All attempts:**
| Tier   | Attempt | Reason |
|--------|---------|--------|
| medium | 1       | Email validation missing — input written to database without format check. |
| medium | 2       | Validation added but returns HTTP 400 instead of 422. |
| high   | 1       | Status code correct but breaks test_valid_registration on line 88. |
| high   | 2       | Custom regex passes + signs but fails Unicode addresses. |

_This Issue is now `needs-human-review`. Leave a comment with guidance and re-run `haive run --milestone 7` to continue._
```

The Issue status is set to `needs-human-review` in the GitHub Project. The orchestrator loop does not block — it continues running any ready tasks. Independent tasks are not affected.

---

### 14. Completion → GitHub Service (`create_milestone_pr`)

When the orchestrator signals `done=True`, all Issues in the Milestone are `complete`. The CLI creates a PR from the milestone branch to main for final human review:

```json
{
  "head_branch": "haive/milestone-7",
  "base_branch": "main",
  "title": "haive milestone 7: Email validation for user registration",
  "body": "## Summary\nAll tasks completed autonomously. See individual task PRs for per-task details and executor notes.\n\n## Tasks completed\n- #101 Add email format validation (merged by haive)\n- #102 Update registration tests (merged by haive)\n- #104 Add documentation (merged by haive)\n\n_Generated by haive. Review individual task PRs for implementation notes and assumptions._"
}
```

This is the single human review gate for the milestone. The human reviews the accumulated changes on the milestone branch and merges to main when satisfied.

---

## What Is Never Passed Between Components

| Item | Why excluded |
|---|---|
| Full file contents | Too large; symbols and snippets from RepoMapService are sufficient |
| Orchestrator reasoning trace | Not needed by executors; would inflate context |
| Review Agent `suggestions` | Consumed by Task Executor retry loop only; orchestrator never sees them |
| Model names in task objects or Issues | Model selection is infrastructure, not task definition |
| Token counts / cost data | Operational metadata; goes to local state file and OTel, not to GitHub or between agents |
| Agent conversation history | Each executor is stateless; no history to pass |
| Outputs of unrelated tasks | Only `blocked_by` task outputs reach an executor |
| Attempt log in GitHub Issues | Internal execution detail; lives in local state for eval, not in the public Issue thread |
