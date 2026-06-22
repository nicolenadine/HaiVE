# Haive — Token Efficiency Strategy

## Purpose

Defines how haive manages token usage: context budgets per task tier, what gets included and excluded from agent prompts, where budgets are enforced, and how the orchestrator's context stays lean over a long-running project. Token efficiency is a first-class concern — not because of cost alone, but because bloated context degrades output quality.

---

## Why This Matters

Every agent call has a context window. Filling it with low-value content wastes tokens and, more importantly, dilutes the signal the model is responding to. A 32k-token prompt where 20k is irrelevant file content produces worse output than an 8k prompt with only relevant content. Cost and quality both improve with a leaner context.

haive runs multiple tasks in parallel. Token inefficiency at the task level multiplies across the run.

---

## Budget Model

Each task gets a **context budget** — the maximum number of tokens the assembled prompt may use. This budget is tier-specific and configurable via `.env`.

```env
TIER_LOW_CONTEXT_BUDGET=8000
TIER_MEDIUM_CONTEXT_BUDGET=16000
TIER_HIGH_CONTEXT_BUDGET=32000
```

These are practical ceilings, not model maximums. Haiku and Sonnet both support 200k context windows — the budgets above are intentionally conservative to preserve output quality and control cost. The numbers are adjustable; the principle is not.

**When a task escalates tiers, its budget increases** — the high-tier attempt gets a larger context window than the medium-tier attempt that preceded it. Reviewer feedback from prior attempts is preserved and carried forward; the expanded budget accommodates both the feedback and richer code context.

**The orchestrator does not control budgets.** It sees task descriptions and verdicts — not code — so it has no basis for judging how much context a task will need. Budget is an infrastructure concern, not a routing concern. The same principle applies here as to model names: the orchestrator defines work, the executor loop manages resources. If budgets are consistently wrong for a project, the fix is tuning `.env`, not adding orchestrator judgment.

**Per-agent budget multipliers (future option).** If a specific agent role consistently needs more context — for example, `database_agent` tasks frequently pull in large schema files and migration history — a static `context_budget_multiplier` field can be added to the agent registry entry:

```yaml
database_agent:
  context_budget_multiplier: 1.5   # 1.5× the tier default
```

This is a human-set configuration value, not a runtime decision. It is applied by the Context Assembler when building the budget calculation. Not implemented in the initial version — add it if Phoenix traces show a specific role consistently hitting its budget ceiling.

---

## Budget Allocation

The context budget is divided across sections in priority order. Higher-priority sections are always included in full. Lower-priority sections are trimmed or dropped if the budget is tight.

| Priority | Section | Token allocation | Notes |
|---|---|---|---|
| 1 (always) | System prompt | Fixed — known at startup from registry | Never trimmed |
| 2 (always) | Task description + acceptance criteria | ~300–500 tokens | Never trimmed |
| 3 (high) | Reviewer feedback from prior attempts | Up to 1000 tokens | Included in full when present; compressed if multiple tiers failed |
| 4 (main) | Code context from RepoMapService | Remainder of budget | Trimmed by ranking when budget is tight |
| 5 (low) | Dependency task outputs | Up to 500 tokens per dependency | Summarized; dropped if budget is exhausted |

**The budget is enforced before assembly**, not after. The Context Assembler calculates how many tokens are available for code context after subtracting sections 1–3 and the dependency allocation, then passes that number to `RepoMapService.get_context_pack(task, available_budget)`. The repo map never returns more than what was asked for.

```
available_for_code_context = total_budget
    - system_prompt_tokens
    - task_description_tokens
    - reviewer_feedback_tokens
    - (dependency_budget_per_task × len(depends_on))
```

---

## Code Context Rules

The RepoMapService returns code context ranked by relevance. The Context Assembler includes symbols in rank order until the budget is reached. The following rules govern what is included and at what granularity.

### What is included

- **Relevant symbols** — function and method bodies ranked by the repo map's PageRank-style graph. Extracted via tree-sitter at the function/method level, not the file level.
- **Class and interface definitions** — signature, field names, and docstring only. Method bodies are included separately if those methods are directly relevant.
- **Broken references** — any symbols referenced in relevant files but with no definition found. Included as a structured list, not as file content.
- **Impacted files** — listed by path only. No content included. Signals to the agent which files it should be careful about affecting.

### What is excluded

- **Full file contents** when a symbol excerpt is sufficient — the repo map returns targeted extracts, not whole files.
- **Test files** as code context — tests are part of the project but rarely needed as context for implementation. The agent is told tests exist and which files they are in; it does not receive test file contents unless the task is explicitly about the tests themselves.
- **Configuration files** unless directly referenced by a relevant symbol.
- **Generated files** (migrations auto-generated by ORM, compiled artifacts, lock files).
- **Entire modules** when only one function within them is relevant.

### Symbol size limits

The repo map extracts symbols via AST and includes the full source of each symbol — there is no mid-function truncation. However, the ranking system naturally limits total size: lower-ranked symbols are dropped when the budget is reached, so only the most relevant code is included. A single very large function (e.g., 500 lines) that ranks first will consume most of the budget; the Context Assembler does not split it. This is intentional — a function that large is the relevant context.

---

## Dependency Output Rules

When a task `depends_on` other tasks, the Context Assembler includes a summary of those tasks' outputs. This gives the sub-agent awareness of what was already done without including the full implementation.

**What is included per dependency:**
- The dependency's task description (one sentence)
- The files it changed (list of paths — not their contents)
- The verdict reason ("All acceptance criteria met")

**What is excluded:**
- The full code written by the dependency's agent
- The dependency's own code context (the current task has its own)
- The dependency's attempt log

**Budget cap:** 500 tokens per dependency. If a task has many dependencies, the Context Assembler includes the most recent ones first and drops older ones if the total dependency allocation would exceed budget. The state file always retains full dependency records — only the context window is trimmed.

```
# Dependency summary format (per depends_on task):
Task task_001: Scaffold UserRegistrationHandler with post() stub.
Changed: src/routes/auth.py, src/models/user.py
Status: complete
```

---

## Retry Feedback Rules

When a task is retried, reviewer feedback from the prior attempt is prepended to the prompt. When a task escalates tiers, all feedback from all prior attempts carries forward.

**Feedback format — single attempt:**
```
Prior attempt failed:
  Reason: Validation added but returns HTTP 400 instead of 422.
  Suggestions:
    - Return 422 Unprocessable Entity, not 400 Bad Request, on validation failure.
    - The error response body should include { "error": "invalid_email" }.
```

**Feedback format — multiple attempts across tiers:**
When three or more attempts have failed and feedback is accumulating, older feedback entries are compressed to their `reason` only (suggestions dropped). The most recent attempt's full feedback is always preserved.

```
Prior attempts (compressed):
  [medium/1] Email validation missing — input written without format check.
  [medium/2] Returns HTTP 400 instead of 422.

Most recent attempt (full):
  [high/1] Status code correct but breaks test_valid_registration on line 88.
  Suggestions:
    - The new validation rejects format "user@domain" — update the regex to allow this.
    - Do not modify the existing test; the test defines the required behavior.
```

**Budget cap:** 1000 tokens for the full feedback block. If the compressed history plus the latest full feedback exceeds this, older compressed entries are dropped from oldest first. The most recent full feedback is always kept.

---

## Orchestrator Context Management

The orchestrator is long-lived and its input grows with every loop as tasks complete, fail, and recover. Without management, a long project run produces a very large task list that inflates the orchestrator's context indefinitely.

### What the orchestrator receives per task (by status)

| Task status | Included in orchestrator input |
|---|---|
| `pending` | task_id, description, agent_role, complexity, depends_on |
| `in_progress` | task_id, status only |
| `complete` | task_id, status, verdict.reason (one line) |
| `failed` (active — needs recovery) | task_id, status, verdict.reason, attempt_log |
| `failed` (resolved — recovery task exists) | task_id, status, verdict.reason only (attempt_log dropped) |
| `blocked` | task_id, status, blocked_by |

### Compression over time

Once a task has been `complete` for more than one orchestrator loop with no dependents waiting on it, it is compressed to a single line in the orchestrator's input:

```
[complete] task_001: Scaffold UserRegistrationHandler — done.
[complete] task_002: Implement post() stub — done.
```

Full detail (including verdict.reason) is kept for tasks completed in the most recent loop — the orchestrator needs to see fresh completions to make its next decomposition decision.

Tasks that have been `complete` for many loops and have no pending dependents can be dropped from the orchestrator's active input entirely. They remain in the state file for the audit trail but no longer appear in the orchestrator's context.

**Implementation:** The orchestrator input builder reads the state file and applies these compression rules before constructing the prompt. The state file itself is never modified — only the view passed to the orchestrator is trimmed.

---

## Enforcement Points

Token budget enforcement happens at two points:

**Token counting method.** `TokenCounter.estimate(text)` uses `math.ceil(len(text) / 4)` — a character-based approximation that requires no model name and no external tokenizer library. The configured budgets (8k / 16k / 32k tokens) are set at roughly 4–16% of the 200k model maximum, so an estimation error of ±20% stays comfortably within the safety margin. Exact per-model token counts are visible in Phoenix traces after the fact (`prompt_tokens` on each LLM span) — use those to calibrate budgets, not to drive pre-call estimates.

**1. Context Assembler (before assembly)**
Calculates the available budget for code context after subtracting fixed sections. Passes the exact budget to `RepoMapService.get_context_pack()`. The repo map never returns more than asked.

**2. RepoMapService (within `get_context_pack`)**
Ranks symbols by relevance and returns them in order until the budget is exhausted. Lower-ranked symbols are dropped. The returned context pack includes a `token_estimate` field so the Context Assembler can verify the assembled prompt is within budget.

There is no post-hoc truncation. If the budget is set correctly, the assembled prompt will be within bounds before it is sent to LiteLLM. If for any reason the assembled prompt exceeds the model's context window (which should not happen if budgets are calibrated), LiteLLM will raise an error — this is caught and treated as a configuration error, not retried.

---

## Budget Calibration Notes

The default budgets are starting points. They should be revisited after observing real task execution:

- If agents consistently produce low-quality output on low-tier tasks, the `TIER_LOW_CONTEXT_BUDGET` may be too small to include sufficient code context.
- If high-tier tasks are expensive but quality is good at medium, `TIER_HIGH_CONTEXT_BUDGET` can be reduced.
- Phoenix traces include token counts per span (`prompt_tokens`, `completion_tokens`) — use these to understand actual usage vs. budget, and to identify tasks where the budget was binding.

The budgets intentionally leave significant headroom below the model's maximum context window. This is deliberate: using 32k of 200k available is not inefficiency — it is precision.
