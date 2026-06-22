# Haive — Model Routing Strategy

## Purpose

Defines how tasks are matched to models: the complexity-to-tier mapping, within-tier fallback behavior, retry and escalation rules, special routing overrides, and the complete `.env` configuration reference. This document is the single source of truth for routing decisions — changing models or retry budgets means editing `.env` only, never code.

---

## Routing in One Sentence

A task's `complexity` determines its starting tier. The tier determines which model list to call. If a model fails with an infrastructure error, LiteLLM transparently tries the next model in the list. If a model produces bad output, haive retries within the same tier. If retries are exhausted, haive escalates to the next tier. If all tiers are exhausted, the task is marked failed and the orchestrator handles recovery.

---

## Tier Definitions

Three tiers map to three cost/capability bands. Each tier is a **list** of models — not a single model — enabling within-tier provider fallback.

| Tier | Starting complexity | Typical models | Purpose |
|---|---|---|---|
| `low` | `low` | Ollama (local) | Simple, well-defined tasks. Zero API cost. |
| `medium` | `medium` | Haiku, GPT-4o-mini | Standard coding tasks. Fast and cheap. |
| `high` | `high` | Sonnet, GPT-4o | Complex or security-sensitive tasks. Best capability. |

**Tasks never start below their complexity tier.** A `high` complexity task goes directly to the high tier — it never touches low or medium.

---

## Failure Modes and Their Routing Behavior

Three distinct failure modes are handled separately. They do not share a counter.

### Mode 1 — API / Infrastructure Error

**Cause:** Rate limit, timeout, 503, provider outage.

**Response:** LiteLLM automatically tries the next model in the current tier's list. Fully transparent to the executor — the executor sees a successful response or a final LiteLLM exception, nothing in between.

**Effect on retry counter:** None. Infrastructure failures do not consume a retry attempt.

**If all models in the tier list fail with infrastructure errors:** Treated as a tier escalation trigger (same as exhausted retries), not a bad-output retry.

---

### Mode 2 — Bad Output (Schema Failure or Review Failure)

**Cause:** Output Validator rejects the response (schema invalid), or Review Agent rejects it (quality failure).

**Response:** Retry within the same tier. Reviewer feedback from the failed attempt is appended to the next attempt's context (see Communication Protocol doc for feedback format).

**Effect on retry counter:** Consumes one attempt from the current tier's `MAX_ATTEMPTS` budget.

**Key distinction:** A schema failure does not invoke the Review Agent. A quality failure does. Both consume a retry.

---

### Mode 3 — Tier Exhausted

**Cause:** `attempt > TIER_*_MAX_ATTEMPTS` after bad output retries.

**Response:** Escalate to the next tier. Feedback from all prior attempts carries forward into the new tier's first attempt. The attempt counter resets to 1 for the new tier.

**Escalation path:**
```
low → medium → high → [write failed verdict, exit executor]
```

There is no tier above `high`. When `high` is exhausted, the executor writes `{ passed: false, reason: <final reviewer reason> }` to the state file and shuts down. The orchestrator handles recovery or escalation to a PR comment.

---

## Retry and Escalation Flow

```
current_tier = tier_for(task.complexity)
attempt = 1
feedback = None

loop:
    try:
        response = litellm.completion(
            model=current_tier.models,   # LiteLLM handles within-list fallback
            messages=assembled_prompt
        )
    except litellm.APIError:
        → treat as tier escalation (all models in tier unavailable)

    if Output Validator fails:
        attempt += 1
        feedback = { "error": "schema_invalid", "detail": ... }
        if attempt > current_tier.max_attempts:
            → escalate or fail
        continue

    verdict = Review Agent(response, task, context_pack)

    if verdict.passed:
        write verdict, push commits, exit ✓

    attempt += 1
    feedback = verdict.suggestions

    if attempt > current_tier.max_attempts:
        if next_tier exists:
            current_tier = next_tier
            attempt = 1
            # feedback carries forward
        else:
            write { passed: false, reason: verdict.reason }
            exit ✗
```

---

## Special Routing Rules

Two rules override the standard complexity-based routing. These are enforced in code, not by the orchestrator — the orchestrator cannot bypass them.

### Rule 1 — `security_reviewer` always starts at high

The `security_reviewer` agent always uses the high tier, regardless of the task's `complexity` field. A low-complexity task that requires security review still sends the security review to the high tier.

**Rationale:** Security judgment requires the best available model. The cost of a cheaper model missing a vulnerability is higher than the cost of running an extra high-tier call.

### Rule 2 — Database migrations always start at high

Any task assigned to `database_agent` whose description or acceptance criteria mention migration, schema change, or `ALTER TABLE` is routed to the high tier, regardless of the orchestrator's complexity rating.

**Rationale:** Migrations are irreversible in production. The cost of a bad migration outweighs any savings from a cheaper model.

**Implementation note:** These overrides are applied in the Task Executor before the tier lookup — not as special fields on the task object. The orchestrator does not need to know about them.

---

## Review Agent Routing

The Review Agent uses a separate model list — `REVIEWER_MODELS` — independent of the task tier system. It does not escalate tiers.

**Rationale:** The Review Agent makes a binary judgment ("did this output meet the acceptance criteria?"). This is a different cognitive task from code generation — a capable-but-cheaper model can often judge well. Using a fixed list also keeps reviewer behavior consistent across task tiers; using a tier-aware reviewer would make the quality bar variable.

**If the Review Agent itself fails** (schema invalid or all reviewer models unavailable): this is treated as a bad-output retry for the sub-agent call. The executor retries the full sub-agent call rather than retrying only the review step.

---

## Recovery Task Tier Selection

Recovery tasks use the same complexity-based tier routing as any other task. There is no special routing rule.

Importantly, by the time an executor writes a `failed` verdict, it has already escalated through all available tiers — a `medium` task that fails has tried medium and then high before giving up. Bumping `complexity` on the recovery task is therefore not meaningful; the high tier was already tried.

The orchestrator's job on recovery is about **task quality**, not tier selection:
- The spec was unclear → rewrite with more precise acceptance criteria
- The task was too large → decompose into two smaller sub-tasks
- The wrong agent role was chosen → route to a different agent
- The approach was wrong → describe a different implementation strategy

The orchestrator reads the failure `reason` and addresses the root cause in the recovery task's description and acceptance criteria. The executor handles tier escalation from there as normal.

---

## LiteLLM Configuration

LiteLLM's `Router` is used to manage the model lists. The router reads the tier lists from config and handles within-tier fallback automatically.

```python
from litellm import Router

router = Router(
    model_list=[
        # Low tier
        {"model_name": "tier_low", "litellm_params": {"model": "ollama/mistral"}},
        {"model_name": "tier_low", "litellm_params": {"model": "ollama/llama3"}},
        # Medium tier
        {"model_name": "tier_medium", "litellm_params": {"model": "claude-haiku-4-5-20251001"}},
        {"model_name": "tier_medium", "litellm_params": {"model": "gpt-4o-mini"}},
        # High tier
        {"model_name": "tier_high", "litellm_params": {"model": "claude-sonnet-4-6"}},
        {"model_name": "tier_high", "litellm_params": {"model": "gpt-4o"}},
        # Reviewer
        {"model_name": "tier_reviewer", "litellm_params": {"model": "claude-haiku-4-5-20251001"}},
        {"model_name": "tier_reviewer", "litellm_params": {"model": "gpt-4o-mini"}},
        # Orchestrator
        {"model_name": "orchestrator", "litellm_params": {"model": "claude-sonnet-4-6"}},
    ],
    fallbacks=[
        {"tier_low":      ["tier_low"]},
        {"tier_medium":   ["tier_medium"]},
        {"tier_high":     ["tier_high"]},
        {"tier_reviewer": ["tier_reviewer"]},
    ],
    routing_strategy="simple-shuffle",
    num_retries=0,       # haive owns retry logic; LiteLLM retries are disabled
)
```

**`num_retries=0`** — haive's executor owns the retry/escalation loop. LiteLLM retries are disabled to prevent double-counting against haive's own attempt budget. LiteLLM only handles within-list provider fallback (infrastructure failures), not bad-output retries.

The `model_list` is built from `.env` at startup — the Python config instantiates the Router from `settings.TIER_LOW_MODELS`, `settings.TIER_MEDIUM_MODELS`, etc. Changing models requires only a `.env` edit and a process restart.

---

## Complete `.env` Reference

```env
# ── Orchestrator ──────────────────────────────────────────────────────────────
ORCHESTRATOR_MODEL=claude-sonnet-4-6

# ── Task Executor Tiers ───────────────────────────────────────────────────────
# Comma-separated lists. LiteLLM tries models left to right on infrastructure error.
# Prefix with provider: ollama/, gpt-, claude- etc (LiteLLM routing format)

TIER_LOW_MODELS=ollama/mistral,ollama/llama3
TIER_LOW_MAX_ATTEMPTS=2

TIER_MEDIUM_MODELS=claude-haiku-4-5-20251001,gpt-4o-mini
TIER_MEDIUM_MAX_ATTEMPTS=2

TIER_HIGH_MODELS=claude-sonnet-4-6,gpt-4o
TIER_HIGH_MAX_ATTEMPTS=2

# ── Review Agent ──────────────────────────────────────────────────────────────
REVIEWER_MODELS=claude-haiku-4-5-20251001,gpt-4o-mini

# ── Orchestrator Recovery ─────────────────────────────────────────────────────
MAX_RECOVERY_DEPTH=3

# ── Concurrency ───────────────────────────────────────────────────────────────
MAX_EXECUTORS=4

# ── Providers ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
OLLAMA_API_BASE=http://localhost:11434

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN=...
GITHUB_REPO=owner/repo
```

---

## Routing Decision Summary

| Situation | Tier used |
|---|---|
| `complexity: low` | TIER_LOW |
| `complexity: medium` | TIER_MEDIUM |
| `complexity: high` | TIER_HIGH |
| Agent role is `security_reviewer` | TIER_HIGH (override) |
| Agent role is `database_agent` + migration | TIER_HIGH (override) |
| Review Agent call | REVIEWER_MODELS |
| Orchestrator call | ORCHESTRATOR_MODEL |
| Infrastructure error, models remain in list | LiteLLM tries next in list (same tier) |
| Bad output, attempts remain | Retry same tier with feedback |
| Attempts exhausted, next tier exists | Escalate to next tier, feedback carries forward |
| All tiers exhausted | Write `failed` verdict, orchestrator rewrites or decomposes the task |
| `lineage_depth > MAX_RECOVERY_DEPTH` | Orchestrator posts PR comment, stops recovery |
