# Haive — Design Decisions Log

Captures significant design choices made during planning, including alternatives considered, tradeoffs acknowledged, and rationale. Intended to prevent re-litigating settled decisions and to explain the "why" behind the architecture to future contributors or future sessions.

Format per entry:
- **Decision**: What was chosen
- **Alternatives**: What else was on the table
- **Rationale**: Why this choice
- **Tradeoff**: What we accept or give up

---

## Configuration

---

### Named configs with an active pointer

**Decision:** Runtime configuration lives in named files at `~/.haive/configs/{name}.env`. A single pointer file (`~/.haive/active`) records which config is currently active. The `haive config` subcommand group handles create, switch, set, and edit without touching `haive run`. If no active config is set, a `default` config is created automatically.

**Alternatives:** Single global `~/.haive/config.env` for everything; per-project `.env` in the project working directory; require `--config` or `--repo` flags on every `haive run` invocation.

**Rationale:** Users have different API keys, repos, and model budgets for different projects or clients. A single global config assumes these are always the same — they are not. A per-project `.env` requires setup in every clone and risks accidental commits of secrets. Flags on every invocation are error-prone and tedious. Named configs give each context its own file, switching is one command, and `haive run` stays clean with no required flags.

**Tradeoff:** Users must remember to switch configs when changing projects (`haive config use <name>`). Forgetting means haive runs against the wrong repo or uses the wrong API keys. Mitigated by `haive config show` printing the active config and repo at the start of every `haive run`, so misconfiguration is visible immediately.

---

## Stack

---

### Language: Python

**Decision:** Python is the primary implementation language.

**Alternatives:** Go, TypeScript.

**Rationale:** The LLM tooling ecosystem is Python-first. LiteLLM, Pydantic, OpenInference instrumentation, and phoenix.evals are all Python libraries with no equivalent in Go or TypeScript. The user's strongest language is also Python.

**Tradeoff:** Go would be more efficient for CPU-bound concurrent work and produces cleaner binaries. However, LLM API calls are the bottleneck in this system — not CPU work — so Go's performance advantages are invisible where they would matter. The complexity of a polyglot codebase (IPC, two dependency systems, two test suites) is not worth the benefit.

---

### Multi-provider LLM calls: LiteLLM

**Decision:** LiteLLM provides a unified API over all model providers and handles within-provider fallback chains.

**Alternatives:** Raw Anthropic SDK only; writing a custom provider abstraction layer.

**Rationale:** LiteLLM solves the hardest architectural problem — routing across providers, fallback when quota is exhausted, cost tracking — in a single dependency. The alternative (custom abstraction) would take weeks and produce something less mature.

**Tradeoff:** LiteLLM is a dependency we don't control. If it adds overhead, breaks an API, or falls behind on provider support, we are exposed. Mitigated by the fact that LiteLLM is widely used and actively maintained. If it ever becomes a problem, the provider interface can be extracted behind an abstraction at that point.

---

### Observability: Arize Phoenix + OpenTelemetry + OpenInference

**Decision:** Instrument with OpenTelemetry (OTel). Use OpenInference semantic conventions for LLM spans. Run Arize Phoenix locally as the backend.

**Alternatives:** Langfuse (proprietary SDK); Helicone (no span hierarchy); LangSmith (LangChain-coupled).

**Rationale:** OTel is a vendor-neutral standard. Instrumentation code is written once against the OTel API — swapping the backend (Phoenix → Langfuse → Honeycomb) requires changing one OTLP endpoint in `.env`, not application code. Phoenix was chosen as the initial backend because it runs fully locally (no SaaS required) and the user wanted exposure to OTel and OpenInference standards.

**Tradeoff:** Langfuse has more mature eval tooling — it supports inline scoring during a run, whereas Phoenix evals (`phoenix.evals`) run as a batch job after the fact. The batch approach is less real-time but more reproducible, and the OTel portability benefit outweighs this. If Phoenix's eval story proves insufficient, Langfuse also accepts OTLP and can be swapped in.

---

### State persistence: JSON files

**Decision:** Run state is persisted to a JSON file (`haive_state.json`) after every state change.

**Alternatives:** SQLite; PostgreSQL; in-memory only.

**Rationale:** JSON files are human-readable, require zero dependencies, are easy to inspect and debug during early development, and double as an audit trail. Restart recovery is simple: load the file on startup.

**Tradeoff:** JSON files do not support efficient queries. If we ever need to query across runs (e.g., "show me all tasks that failed in the last 7 days"), we will need to migrate to SQLite or a proper database. This is an explicit deferral, not an oversight — query patterns should be observed before a storage layer is chosen.

---

### CLI framework: Typer

**Decision:** Typer for the CLI entry point.

**Alternatives:** Click (what Typer wraps); argparse; a custom REPL.

**Rationale:** Typer uses Python type hints instead of decorators, making CLI definitions readable and maintainable with less boilerplate. It is built on Click, so the full Click ecosystem is available if needed.

**Tradeoff:** Typer is a third-party dependency. Minimal risk — it is stable, widely used, and closely tracks Click.

---

## Architecture

---

### Task Executors are stateless disposable workers

**Decision:** Each task gets a fresh Task Executor with a clean context window. Executors do not retain state between tasks and have no shared memory.

**Alternatives:** Long-lived agents that accumulate conversation history; a single agent loop that handles all tasks sequentially.

**Rationale:** Disposable workers keep context windows lean and predictable. A failed or misbehaving executor does not contaminate the next task. Independent tasks can run as parallel workers with no risk of interference. The orchestrator is the only agent that needs long-running context.

**Tradeoff:** Each executor must receive its full context in a single shot — there is no back-and-forth clarification. This makes the Context Assembler's job critical: if it assembles insufficient context, the task will fail. This is a design forcing function: context must be explicit and complete.

---

### Orchestrator sees only verdicts, never full agent output

**Decision:** The orchestrator receives `{ passed: bool, reason: str }` per task. It never receives code, review prose, test output, or any content produced by sub-agents.

**Alternatives:** Orchestrator receives full sub-agent output to make more informed routing decisions.

**Rationale:** The orchestrator's job is sequencing work, not evaluating code quality. If it receives full outputs, its context grows with every completed task and it must reason about content outside its domain. The Review Agent is specifically responsible for quality judgment — the orchestrator trusts that verdict.

**Tradeoff:** The orchestrator cannot make nuanced routing decisions based on partial output quality. For example, if a task partially succeeded, the orchestrator only knows "failed" — not "70% there." This is acceptable because the retry/escalation loop within the Task Executor already handles partial success by including reviewer suggestions in the next attempt.

---

### Separate Review Agent (LLM-as-judge)

**Decision:** A dedicated Review Agent evaluates sub-agent output quality. The orchestrator does not do this evaluation itself.

**Alternatives:** Orchestrator reviews its own task outputs; output validator handles all quality checks deterministically.

**Rationale:** Quality judgment is role-specific — what "good" means for a code reviewer's output is different from a test generator's output. The orchestrator would have to understand all output types to review them. A separate Review Agent has a narrower system prompt and is independently testable. Its verdicts and suggestions also feed directly into the retry loop with structured context.

**Tradeoff:** An extra LLM call per task in the critical path. For a 10-task run, that is 10 additional reviewer calls. Mitigated by routing the reviewer to a cheaper model tier (`REVIEWER_MODELS` in `.env`).

---

### Context Assembler is fully deterministic

**Decision:** The Context Assembler builds each agent's prompt mechanically from structured task data, resolved file references, and prior attempt feedback. No LLM call.

**Alternatives:** Use an LLM to assemble the most "relevant" context from a broader pool of information.

**Rationale:** LLM-assembled context would add latency, cost, and unpredictability to every task. More importantly, an LLM assembler would need to reason over large amounts of codebase content to determine relevance — expensive and a context window risk. By requiring the orchestrator to produce explicit file references (resolved by the Code Discoverer), context assembly becomes a pure data transformation.

**Tradeoff:** This places a responsibility on the orchestrator: task descriptions must be specific enough for the Code Discoverer to find the right files. Vague tasks produce poor context. This is a design forcing function — it discourages vague task decomposition, which is desirable anyway.

---

### RepoMapService: Aider repo map approach with incremental invalidation

**Decision:** Code discovery and context retrieval is handled by a dedicated `RepoMapService` backed by DuckDB. It uses `tree-sitter` to build a structural graph of the codebase (files, symbols, references, edges) and a PageRank-style ranker to score file relevance for each task. No vector embeddings for the initial version. The Task Executor is the sole caller — it calls `get_context_pack()` at task start and `update_files()` at task end. The Task Scheduler has no RepoMapService involvement. The Context Assembler and Review Agent receive data from the context pack; they do not call the service directly.

**Alternatives:** Simple ripgrep + AST lookup (no graph, no ranking); LLM-based semantic search; vector embeddings + Chroma/Qdrant.

**Rationale:** The Aider repo map approach is more accurate than raw ripgrep (which fails when task terminology diverges from code vocabulary) and fully deterministic/reproducible (same code + same task → same result, unlike vector similarity which is model-dependent). The graph structure also enables broken reference detection and impact analysis — knowing which files reference a changed symbol is valuable for test targeting and reviewer context. Vector semantic search was considered as a secondary fallback and may be added later, but the graph approach covers the majority of cases without embeddings.

**Tradeoff:** More complex than ripgrep. Requires tree-sitter parsers per language. The graph must be kept fresh as code changes. Mitigated by incremental invalidation — only changed files are re-parsed, not the whole codebase.

---

### Incremental repo map invalidation using content hashes

**Decision:** The RepoMapService uses content hashes to detect changed files and re-parses only those files. Stores `parser_version` and `extractor_version` alongside each file entry — if parser logic changes, old entries are invalidated even if file content has not changed. Git (`git diff --name-only`, `git status --porcelain`) is the source of truth for which files changed after an agent edit — not agent self-reporting.

**Alternatives:** Full rebuild on every run; file-watcher daemon.

**Rationale:** Full rebuild is correct but slow for large codebases. Incremental invalidation is fast and equally correct when hashing is reliable. Git as source of truth prevents incorrect behavior if an agent crashes, misreports, or edits more files than declared.

**Tradeoff:** Content hashing adds a small overhead per file check. The `extractor_version` field requires discipline — it must be bumped when parser logic changes, or the cache silently serves stale entries. A startup validation that checks version consistency mitigates this.

---

### DuckDB for RepoMapService storage

**Decision:** The RepoMapService uses DuckDB as its backing store, separate from the task state file (which stays as JSON).

**Alternatives:** SQLite; PostgreSQL; raw JSON files.

**Rationale:** DuckDB is zero-infrastructure (no server process, single file, Python library) like SQLite, but designed for analytical queries — graph traversal, ranking, aggregations — which are exactly the queries the RepoMapService runs. Better query performance than SQLite for this workload without the operational overhead of PostgreSQL. The two storage concerns (run state and repo map) have different query patterns and are intentionally kept separate.

**Tradeoff:** DuckDB is less widely known than SQLite. Concurrent write access is limited (one writer at a time) — acceptable because the Task Scheduler serializes repo map refreshes between task executions. If haive ever becomes a multi-user shared service, PostgreSQL + pgvector becomes the right upgrade path (it would also consolidate the graph store with future vector embeddings).

---

### No orchestrator file tree

**Decision:** The orchestrator does not receive a file tree or any file contents.

**Alternatives:** Provide the orchestrator with a directory listing so it can reference files when decomposing tasks.

**Rationale:** The orchestrator's job is decomposing objectives into tasks — reasoning about what work needs to be done, not where code lives. File discovery is the Code Discoverer's job. Including a file tree in the orchestrator's context adds tokens on every loop iteration without providing value for task decomposition.

**Tradeoff:** The orchestrator cannot check whether a module already exists before creating a task to scaffold it. If this becomes a practical problem (duplicate file creation), the orchestrator can be given a tool call to check file existence on demand — not a file tree loaded into context by default.

---

### Three distinct failure modes with separate handling

**Decision:** API/infrastructure errors, bad output quality failures, and tier exhaustion are handled separately and explicitly.

| Failure | Handler |
|---|---|
| API / infra error | LiteLLM within-tier fallback (transparent to executor) |
| Bad output | Task Executor retry loop with reviewer feedback |
| Tier exhausted | Escalation to next tier or HUMAN_CHECKPOINT |

**Alternatives:** Treat all failures as retries; use a single unified retry counter across all failure types.

**Rationale:** Conflating these produces bad behavior. A rate limit error does not mean the output was bad — retrying with the same model wastes attempts. A bad output does not mean the provider is down — switching providers immediately wastes the retry budget on a different model before it was needed.

**Tradeoff:** More logic to implement and reason about. The separation is worth it because each failure type has a clearly correct response that is wrong for the other types.

---

### Retry feedback carries forward across tier escalation

**Decision:** Reviewer suggestions from failed attempts are included in the prompt for subsequent attempts, including when escalating to a higher model tier.

**Alternatives:** Reset context on tier escalation; only carry feedback within a tier.

**Rationale:** If an attempt produced output that was 70% correct, that partial progress is valuable signal for the next attempt — regardless of which model handles it. Dropping the feedback on escalation wastes a learning opportunity and may produce a completely different (not necessarily better) result.

**Tradeoff:** Context grows with each failed attempt, which increases token usage and cost. For tasks that exhaust multiple tiers, the prompt can become large. Acceptable given that reaching the high tier means cheaper models have already failed — the cost of a longer prompt at Sonnet/Opus tier is justified.

---

### Model configuration in named config, not in agent definitions

**Decision:** All model names, tier lists, and retry budgets are in the active named config (`~/.haive/configs/<active>.env`). Agent registry entries contain no model references.

**Alternatives:** Model names in agent YAML (as hints or hard assignments); model selection in code.

**Rationale:** Separating model configuration from agent definitions means you can change models everywhere with a single `haive config set` call and no code or YAML changes. Agent definitions define capability; the config defines the resource constraints. Swapping `claude-sonnet-4-6` to `claude-opus-4-8` for the high tier is a one-line change.

**Tradeoff:** Indirection — you have to look in two places to understand what model will run for a given task. Mitigated by clear naming conventions in the config and `haive config show`.

---

### Complexity as a single field: max(coding_difficulty, security)

**Decision:** Each task has a single `complexity` field with values `low`, `medium`, `high`. It represents `max(coding_difficulty, security_sensitivity)`.

**Alternatives:** Two separate fields for coding difficulty and security risk; a numeric score.

**Rationale:** Downstream components (Model Router, Task Scheduler) only need to know which tier to use. Whether a task is complex because of algorithmic difficulty or security sensitivity, the result is the same: a higher-tier model. Tracking both dimensions separately adds schema complexity with no practical benefit at the routing layer.

**Tradeoff:** Loss of nuance. A task that is security-sensitive but trivially simple (e.g., adding a permission check) gets routed to the same tier as a task that is both complex and security-sensitive. Acceptable — routing conservatively on security is the correct default.

---

### Task Scheduler as a separate deterministic component

**Decision:** A dedicated Task Scheduler evaluates the dependency graph and manages the executor pool. It is not part of the orchestrator.

**Alternatives:** Orchestrator manages task sequencing and concurrency directly; a simple sequential task runner.

**Rationale:** The orchestrator produces work; the scheduler runs it. These are different responsibilities with different cadences — the orchestrator runs in coarse-grained loops (per objective chunk), the scheduler runs continuously. Keeping them separate makes both simpler and allows the scheduler to be fully deterministic (DAG traversal, semaphore management) with no LLM involvement.

**Tradeoff:** Another component to implement and reason about. Worth it because it enables true parallelism (independent tasks run simultaneously) and makes the concurrency cap (`MAX_EXECUTORS`) a clean configuration concern.

---

### Blocked tasks: continue independent work

**Decision:** When a task fails, its dependents are marked `blocked` but independent tasks continue running.

**Alternatives:** Halt the entire run on any task failure.

**Rationale:** A failed `code_editor` task for one module should not stop a `documentation_writer` task for a completely different module. Maximum forward progress is preferable; blocked tasks and their reasons are surfaced in the final summary for human review.

**Tradeoff:** The run may do work that becomes irrelevant if a core task has failed. For example, if scaffolding fails, the implementation task depending on it is blocked — but other unrelated tasks continue, potentially producing output that needs to be re-evaluated once the scaffold issue is resolved. Acceptable because wasted work is recoverable; a halted run loses more time.

---

### GitHub PR as the unit of work

**Decision:** Haive receives a GitHub PR number as its input. The PR title and body define the objective. PR comments are the bi-directional communication channel between the orchestrator and the human. Haive does not create PRs.

**Alternatives:** Free-text objective passed via CLI; a structured task file the human maintains locally; a custom project management tool.

**Rationale:** PRs are already the natural unit of work in software development. They have a built-in spec (description), a communication channel (comments), a code surface (branch), CI integration, and a review/merge workflow. Using the PR as the input means haive fits into existing development workflows rather than introducing a parallel system. All context — the spec, the human's guidance, haive's progress updates — lives in one place that the human already monitors.

**Tradeoff:** Haive requires a GitHub connection and the PR must be pre-created before haive is invoked. An external tool or human is responsible for translating a build plan into PRs — haive does not manage project-level prioritization. This is acceptable and intentional: project management is a different layer, and haive stays focused on implementation.

---

### PR comments as the human-orchestrator communication channel

**Decision:** When the orchestrator cannot recover from a task failure, it posts a structured comment on the PR. The human responds via a PR comment. The orchestrator reads new comments on every loop.

**Alternatives:** Blocking CLI prompt (human must be present at the terminal); a separate notification/webhook system; email or Slack integration.

**Rationale:** PR comments are async, persistent, and visible in context alongside the code and the spec. The orchestrator never blocks the run on human input — it posts the escalation and continues working on independent tasks. When the human responds (minutes or hours later), the orchestrator picks it up on its next loop. The conversation history in the PR is also a natural audit trail: you can see what haive tried, why it failed, and what guidance the human provided.

**Tradeoff:** The human must monitor PR comments to notice escalations. There is no active push notification from haive beyond the PR comment itself. Future improvement: integrate with GitHub notification settings or optionally post to Slack via a webhook — but that is outside haive's scope and can be wired at the GitHub level.

---

### Orchestrator recovery before escalation: lineage tracking

**Decision:** When a task fails, the orchestrator attempts recovery by creating new tasks with revised descriptions or decompositions (`recovery_for`, `lineage_depth` fields). Escalation to a PR comment only happens when the orchestrator judges recovery impossible or when `lineage_depth > MAX_RECOVERY_DEPTH`.

**Alternatives:** Escalate to human immediately on any task failure; escalate after N total failures across the whole run.

**Rationale:** Most task failures are recoverable — the orchestrator often has enough information from the failure `reason` to create a better-targeted follow-up task. Involving a human on every failure is disruptive and wastes the orchestrator's ability to self-correct. The lineage depth limit (`MAX_RECOVERY_DEPTH`, configurable via `.env`) is the hard backstop that prevents infinite recovery loops.

**Tradeoff:** The orchestrator may spend tokens on recovery attempts that ultimately fail. This is acceptable — the cost of a few extra LLM calls is lower than the cost of interrupting a human for problems the system could resolve itself.

---

## Agent Model

---

### Many specialized agents over fewer general-purpose agents

**Decision:** Agents have narrow, specific responsibilities. Multiple specialized coding agents exist rather than one general coding agent.

**Alternatives:** One general `coding_agent` that handles all code tasks; a small set of broad agents.

**Rationale:** Narrow agent definitions produce better system prompts, more predictable output, and clearer routing. A general coding agent needs a system prompt that covers all task types, which is harder to write well and harder to evaluate. Specialized agents can be given precise constraints and quality criteria.

**Tradeoff:** More agents to define, maintain, and evaluate. More routing decisions for the orchestrator. Mitigated by the orchestrator having clear, non-overlapping descriptions and skills lists for each agent. Skills overlap is an explicit design concern flagged during agent definition.

---

### Dedicated security_reviewer separate from code_reviewer

**Decision:** Security review is a dedicated agent, not a skill or mode of the general code reviewer.

**Alternatives:** Code reviewer handles security concerns as part of general review; security as a flag passed to the code reviewer.

**Rationale:** Security review requires a fundamentally different lens — looking specifically for exploitable vulnerabilities rather than general code quality. A combined agent would need a system prompt that covers both, diluting focus. A dedicated security reviewer can be more thorough, uses a higher model tier by default, and makes it easy to route high-risk tasks explicitly.

**Tradeoff:** Two review agents means some tasks may go through both — adding cost. This is intentional for high-risk tasks. Low-risk tasks only go through `code_reviewer`.

---

### The scaffold → implementation → code_editor sequence

**Decision:** Three separate agents handle the code creation lifecycle: `scaffold_agent` creates file structure and stubs, `implementation_agent` fills in logic bodies, `code_editor` modifies working code.

**Alternatives:** Two agents (create and modify); one general coding agent.

**Rationale:** Each step has meaningfully different context, constraints, and success criteria. Scaffold: blank slate, produces interfaces. Implementation: stubs defined, fulfills the contract, often driven by tests. Editing: working code, preserves existing behavior while adding or changing something. Conflating any two of these produces a system prompt that is harder to write and an agent that is harder to evaluate.

**Tradeoff:** The orchestrator must understand the three-step sequence and create tasks accordingly. Incorrect routing (e.g., sending an implementation task to `code_editor`) will produce worse results. Mitigated by explicit orchestrator rules documented in the agent model.

---

### Prompt versioning with archive directory

**Decision:** Each agent registry entry has a `prompt_version` semver field. Current prompts live in `prompts/`. Previous versions are archived in `prompts/archive/{agent_name}/`.

**Alternatives:** Rely on git history for prompt versioning; no versioning.

**Rationale:** Git history is not surfaced in runtime artifacts. When debugging a Phoenix trace from three months ago, you cannot easily recover which prompt version was active at that time without additional tooling. Explicit versioning in the registry — recorded in the state file and OTel spans — makes this lookup trivial.

**Tradeoff:** Manual discipline required — `prompt_version` must be bumped and the old prompt archived whenever a prompt changes. If this is forgotten, the version record becomes inaccurate. A startup validation that hashes the current prompt file and compares it to a stored hash can catch this automatically.

---

### Migration tasks always require a security_reviewer dependency

**Decision:** Any `database_agent` task involving a migration must always be followed by a `security_reviewer` task. This is a hard rule, not left to orchestrator judgment.

**Alternatives:** Rely on well-written acceptance criteria to cover migration safety; make it orchestrator-discretion.

**Rationale:** Database migrations are uniquely high-risk: irreversible operations, potential data loss, and production table locks. The cost of a security review on every migration is low compared to the cost of a missed destructive operation. Making it a hard rule removes the dependency on the orchestrator consistently writing thorough-enough acceptance criteria.

**Tradeoff:** Every migration incurs a security reviewer call even for trivial migrations (e.g., adding an index). Acceptable — the cost of a cheap reviewer call is far less than the risk of skipping it.

---

### Refactoring scope enforced by file list, not line count

**Decision:** The `refactoring_agent` is constrained to only touch files listed in the task context. The system prompt makes this a hard constraint. The Review Agent rejects outputs that modify unlisted files.

**Alternatives:** Set a maximum line-change budget; rely on the agent to self-limit.

**Rationale:** A file list constraint is semantically meaningful and checkable. The Review Agent can deterministically verify which files were changed. A line count limit is arbitrary (what is the right number?), not semantically linked to task scope, and harder to enforce. Relying on the agent to self-limit is not reliable.

**Tradeoff:** A refactoring task that legitimately needs to touch more files than anticipated must be re-decomposed into multiple tasks by the orchestrator. This is the correct behavior — scope should be made explicit upfront, not discovered mid-execution.
