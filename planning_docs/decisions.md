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

**Status:** Superseded — see "Agentic Code Discovery Agent replaces the structural repo graph" below. Kept here for historical context on why the graph-based approach was tried first and why it was replaced.

**Decision:** Code discovery and context retrieval is handled by a dedicated `RepoMapService` backed by DuckDB. It uses `tree-sitter` to build a structural graph of the codebase (files, symbols, references, edges) and a PageRank-style ranker to score file relevance for each task. No vector embeddings for the initial version. The Task Executor is the sole caller — it calls `get_context_pack()` at task start and `update_files()` at task end. The Task Scheduler has no RepoMapService involvement. The Context Assembler and Review Agent receive data from the context pack; they do not call the service directly.

**Alternatives:** Simple ripgrep + AST lookup (no graph, no ranking); LLM-based semantic search; vector embeddings + Chroma/Qdrant.

**Rationale:** The Aider repo map approach is more accurate than raw ripgrep (which fails when task terminology diverges from code vocabulary) and fully deterministic/reproducible (same code + same task → same result, unlike vector similarity which is model-dependent). The graph structure also enables broken reference detection and impact analysis — knowing which files reference a changed symbol is valuable for test targeting and reviewer context. Vector semantic search was considered as a secondary fallback and may be added later, but the graph approach covers the majority of cases without embeddings.

**Tradeoff:** More complex than ripgrep. Requires tree-sitter parsers per language. The graph must be kept fresh as code changes. Mitigated by incremental invalidation — only changed files are re-parsed, not the whole codebase.

---

### Incremental repo map invalidation using content hashes

**Status:** Superseded — see "Agentic Code Discovery Agent replaces the structural repo graph" below. The git-as-source-of-truth principle for detecting changed files carries forward into `FileIndexService`; the content-hash/symbol-reparse machinery does not.

**Decision:** The RepoMapService uses content hashes to detect changed files and re-parses only those files. Stores `parser_version` and `extractor_version` alongside each file entry — if parser logic changes, old entries are invalidated even if file content has not changed. Git (`git diff --name-only`, `git status --porcelain`) is the source of truth for which files changed after an agent edit — not agent self-reporting.

**Alternatives:** Full rebuild on every run; file-watcher daemon.

**Rationale:** Full rebuild is correct but slow for large codebases. Incremental invalidation is fast and equally correct when hashing is reliable. Git as source of truth prevents incorrect behavior if an agent crashes, misreports, or edits more files than declared.

**Tradeoff:** Content hashing adds a small overhead per file check. The `extractor_version` field requires discipline — it must be bumped when parser logic changes, or the cache silently serves stale entries. A startup validation that checks version consistency mitigates this.

---

### DuckDB for RepoMapService storage

**Status:** Superseded — see "Agentic Code Discovery Agent replaces the structural repo graph" below. With the graph dropped, there are no analytical/traversal queries left to justify DuckDB; `FileIndexService` stores its output as plain markdown files on disk and relies on git for change detection.

**Decision:** The RepoMapService uses DuckDB as its backing store, separate from the task state file (which stays as JSON).

**Alternatives:** SQLite; PostgreSQL; raw JSON files.

**Rationale:** DuckDB is zero-infrastructure (no server process, single file, Python library) like SQLite, but designed for analytical queries — graph traversal, ranking, aggregations — which are exactly the queries the RepoMapService runs. Better query performance than SQLite for this workload without the operational overhead of PostgreSQL. The two storage concerns (run state and repo map) have different query patterns and are intentionally kept separate.

**Tradeoff:** DuckDB is less widely known than SQLite. Concurrent write access is limited (one writer at a time) — acceptable because the Task Scheduler serializes repo map refreshes between task executions. If haive ever becomes a multi-user shared service, PostgreSQL + pgvector becomes the right upgrade path (it would also consolidate the graph store with future vector embeddings).

---

### RepoMap scanner depends on a complete .gitignore

**Decision:** `scan_repo()` respects `.gitignore` using fnmatch-style pattern matching and applies it at the directory level during the walk — directories matching any gitignore pattern are skipped entirely, not just filtered at the file level. The only hardcoded exception is `.git`, which cannot appear in `.gitignore` by design. All other exclusions (`.venv`, `node_modules`, `__pycache__`, `dist`, etc.) are expected to be in the project's `.gitignore`.

**Alternatives:** Hardcode a known-bad directory list in the scanner; ship a default exclusion list alongside the scanner.

**Rationale:** Hardcoding exclusions in the scanner is a maintenance problem — the list of directories to skip is project- and ecosystem-specific (Python projects have `.venv`, Node projects have `node_modules`, etc.). The project's `.gitignore` is already the authoritative source of "what should not be tracked" and is maintained by the project author. Respecting it is correct and avoids duplicating that knowledge.

**Tradeoff:** If the project's `.gitignore` is incomplete or missing, `scan_repo()` will index everything it can walk — including installed packages in `.venv`, compiled artifacts in `dist/`, etc. This has severe consequences for the ranker: packages with many cross-file references dominate PageRank and drown out project files entirely. Validated during hands-on testing: scanning without `.venv` in `.gitignore` indexed 15,477 files and returned nacl exception classes as the top-ranked context for a CLI task. With a complete `.gitignore`, the same run indexed 65 files and produced relevant results. The user is responsible for maintaining a complete `.gitignore`. Haive surfaces this in its README.

**Note:** The ranker this decision originally protected is superseded (see below), but the gitignore-respecting directory walk itself carries forward unchanged into `FileIndexService`, which needs the same exclusion behavior when generating `agent.md` files.

---

### Agentic Code Discovery Agent replaces the structural repo graph

**Decision:** Code discovery moves from a deterministic graph (DuckDB + tree-sitter + PageRank-style ranking) to an agentic, tool-calling LLM agent that navigates per-directory `agent.md` index files to find task-relevant files and sections.

**Alternatives:** Keep the tokenized-query + IDF + Personalized PageRank fix (see the now-superseded `RepoMapService` decisions); a hybrid where the LLM agent is only invoked when keyword matching finds nothing.

**Rationale:** Keyword/symbol matching has a hard ceiling: it only works when a task description happens to contain literal identifiers from the codebase. Because the orchestrator deliberately never sees code (see "No orchestrator file tree"), most task descriptions are natural language with no code vocabulary to match against. Hands-on testing confirmed the ceiling in practice — even after fixing the tokenization bug, test files and incidental keyword collisions dominated the top ranks for realistic tasks. An agent that reads structured, human-curated-equivalent summaries (`agent.md`) can reason about relevance the way a human skimming a directory listing would, regardless of whether the task happens to name a symbol.

**Tradeoff:** Adds one or more LLM calls per task in the discovery step, where the old approach was a free deterministic computation. Discovery results are no longer perfectly reproducible run-to-run. Mitigated by routing discovery to the cheapest model tier and by the fact that the old approach's "free" computation was producing low-quality results that themselves required a retry/escalation slot to recover from.

---

### Per-directory agent.md index maintained by FileIndexService

**Decision:** Each source directory has an `agent.md` file listing its files, one-line descriptions, and (optionally) key symbols with line ranges. These files are generated by a new `FileIndexService` at `haive index` time (covering the whole repo) and regenerated automatically as a post-task step — never via a startup scan.

**Alternatives:** Developer-maintained `agent.md` files; a single repo-wide index file instead of per-directory; regenerate by scanning the whole repo on every `haive run` startup.

**Rationale:** Requiring developers to track and update `agent.md` whenever files are added, modified, or deleted is a sync burden with no enforcement mechanism — it will drift. Automatic maintenance inside the application guarantees consistency. A startup scan was explicitly rejected: haive's own task agents are the only thing that mutates the repo during a run, so detecting what changed after each task (via git) is sufficient to keep the index correct — scanning the entire repo at the start of every invocation would be wasted work.

**Tradeoff:** First-run generation (`haive index`) has an up-front cost proportional to repo size. Regeneration logic must correctly map changed files to the directories whose `agent.md` needs updating — get this wrong and the index silently drifts. Mitigated by the structural validator (see below) catching format drift, though it cannot catch stale-but-well-formatted content.

---

### Code Discovery Agent is agentic with guardrails, not single-shot

**Decision:** The Code Discovery Agent is a tool-calling agent (tools: read a directory's `agent.md`, list subdirectories) that explores top-down from the repo root, descending into subdirectories only when their parent's `agent.md` suggests relevance. It is bounded by an explicit token budget, a max exploration depth/tool-call count, and a required structured output schema.

**Alternatives:** Single-shot call with every `agent.md` in the repo stuffed into one prompt; a fully deterministic algorithm (e.g., embeddings) instead of an LLM.

**Rationale:** Progressive disclosure means a well-organized repo rarely requires reading more than a handful of `agent.md` files — only the directories actually relevant to the task. Stuffing the whole tree into one prompt scales badly and reintroduces the context-bloat problem this design is trying to avoid. Explicit guardrails (depth limit, call-count limit, token budget) prevent an agentic loop from over-exploring an unfamiliar or large repo.

**Tradeoff:** More complex to design and prompt-engineer than a single-shot call — guardrails must be tuned empirically. Worth it because the alternative (single-shot, full-tree context) doesn't actually solve the scaling problem RepoMapService had.

---

### Discovery output is structured sections; ContextAssembler stays I/O-free

**Decision:** The Code Discovery Agent returns a structured list of `{file, symbol, start_line, end_line, full, reason}` (or an empty list). `FileIndexService` is responsible for reading those files/sections from disk and producing loaded source text. `ContextAssembler` receives already-loaded content and performs no file I/O of its own.

**Alternatives:** Have `ContextAssembler` read and slice files directly from the discovery output.

**Rationale:** "Context Assembler is fully deterministic" (see above) was an explicit no-I/O design constraint from Step 16's original design. Folding file-loading into `ContextAssembler` would violate that and mix "fetch content" with "format prompt." `FileIndexService` already needs file access for `agent.md` generation and regeneration, so giving it section-loading too keeps all file-content access under one component with one coherent responsibility, while `ContextAssembler` stays a pure formatting function.

**Tradeoff:** None significant — this is a cleaner restatement of an existing constraint, not a new one.

---

### Token budget enforced at section loading, not at discovery

**Decision:** `CodeDiscoveryAgent` outputs sections in order of decreasing relevance (most important first) but does not attempt to enforce a token budget. Token budget enforcement is the responsibility of `FileIndexService.load_sections()`, which processes sections in the order given, accumulates an estimated token count via `TokenCounter.estimate()`, and stops loading once the next section would exceed the budget.

**Alternatives:** Have the discovery agent count tokens before selecting sections; enforce the budget in `ContextAssembler`.

**Rationale:** The discovery agent only reads `agent.md` index files, not the actual source files it is selecting. It therefore has no basis for counting the tokens those source files contain — asking it to enforce a budget would be asking it to guess. Enforcement at `load_sections()` is the first point in the pipeline where actual file content is available and can be measured. `ContextAssembler` is deliberately I/O-free and receives pre-loaded content, so it cannot enforce a budget either. The agent's contribution to budget management is to rank sections by relevance, so that when the loader stops at the budget limit, the dropped sections are the least important ones.

**Tradeoff:** The agent's relevance ordering is LLM-produced and not perfectly reproducible. If the agent misjudges relevance ordering, lower-priority sections may be loaded while higher-priority ones are dropped. Mitigated by the fact that the same model is reading the same structured agent.md summaries each time and the task description is deterministic — ordering tends to be stable for a given task.

---

### agent.md format validated by a pure-Python structural validator

**Decision:** A deterministic, non-LLM validator checks generated `agent.md` files against a fixed structural format (required section headers, per-file line format, no prose paragraphs, line count limits). It runs automatically after generation (with bounded retries on failure) and is exposed via `haive index --validate` to check existing files without regenerating them.

**Alternatives:** Trust the generating LLM's output as-is; validate format using a second LLM call.

**Rationale:** Format compliance is a mechanical, checkable property — it doesn't require judgment, so it shouldn't cost an LLM call. A pure-Python validator is fast, deterministic, and catches a small/cheap model's generation mistakes (a likely failure mode for the low-tier model used here) before they degrade discovery quality.

**Tradeoff:** Only catches format violations, not semantic inaccuracies (e.g., a wrong one-line description). The validator's rules must be kept in sync with the format spec as it evolves.

---

### agent.md generation uses tool-calling to read source files, not filenames alone

**Decision:** `AgentMdGenerationAgent` (Step 12) exposes a `read_file` tool and lets the LLM read each source file in full before writing the `agent.md`. File content is never passed as a block in the prompt. The agent reads files on demand via tool calls, then produces the `agent.md` as its final response.

**Alternatives:** Pass filenames only (original implementation — LLM hallucinates symbol names and line numbers); pass full file content as prompt text; use AST extraction for symbols and pass content for descriptions only.

**Rationale:** Passing filenames only causes the LLM to invent class names, method names, and line numbers it has never seen. Passing file content in the prompt works but requires pre-loading everything into the call whether the model needs it or not, and doesn't compose well with the incremental update path. Tool-calling lets the model read exactly what it needs, fits naturally into the `call_single()` pattern already established for `CodeDiscoveryAgent`, and produces accurate symbols and descriptions because the model has seen the actual code. The initial full-repo scan cost is a one-time expense; subsequent updates are per-changed-file only.

**Tradeoff:** More LLM calls per directory (one per file read) versus a single prompt-stuffed call. At low-tier model prices and with incremental updates limiting re-work, this is acceptable. The accuracy gain justifies the additional calls.

---

### Incremental agent.md updates: deletions in code, reads only changed files

**Decision:** `update_after_task` (Step 15) handles the three change types differently: **deletions** are handled entirely in code (parse the existing `agent.md`, strip the deleted file's entry and its symbol sub-entries — no LLM call); **additions and modifications** call `AgentMdGenerationAgent.update()`, which receives the current `agent.md` content and reads only the added/modified files via the `read_file` tool, preserving unchanged entries verbatim. Unchanged files in the same directory are never re-read.

**Alternatives:** Re-generate the entire `agent.md` from scratch for any directory with a changed file (simpler but re-reads all files even if only one changed).

**Rationale:** Full regeneration on any change would re-read every file in a directory whenever any single file is modified — wasteful for large directories and unnecessary since unchanged entries are already correct. Deletions need no model reasoning at all (just text manipulation). Surgical updates keep costs proportional to the amount of code that actually changed, which is the steady-state operation after the one-time initial scan. This also avoids drift: if the agent is asked to regenerate entries it didn't read, it may alter them based on stale assumptions.

**Tradeoff:** The update prompt must instruct the model to preserve unchanged entries exactly, and the validator still checks the whole file after update. If the model accidentally rewrites entries it was told to preserve, the validation retry loop catches format violations but not content drift. Mitigated by explicit prompt instruction and by the fact that unchanged entries are shown in the prompt — the model has them as reference.

---

### Low-tier model for agent.md generation and Code Discovery Agent

**Decision:** Both `agent.md` generation and the Code Discovery Agent route to the cheapest configured model tier by default, through the existing named-config tier system (no new configuration mechanism).

**Alternatives:** Use the same tier as task execution agents; hardcode a specific model rather than going through tier config.

**Rationale:** Both tasks are low-reasoning and structured — summarizing a directory's contents, or navigating a small set of structured documents to pick relevant ones. Neither requires the reasoning depth that justifies a higher-tier model's cost. This is consistent with "Model configuration in named config, not in agent definitions" — no special-casing needed.

**Tradeoff:** If the low tier under-explores or mis-summarizes in practice, discovery quality suffers. If this is observed empirically, a higher tier (e.g., Sonnet) can be configured for discovery specifically without any code change — that's the explicit fallback, not a redesign.

---

### Discovery emptiness tracked as structured metadata for the Reviewer Agent

**Decision:** Every task execution records a `discovery_status` (`found` / `empty_expected` / `empty_unexpected`) and a short `discovery_note`, derived from whether the Code Discovery Agent found relevant sections and whether the task's `agent_role` is a role expected to need existing code (e.g., `scaffold_agent` legitimately finds nothing). This is passed to the Review Agent as an explicit structured field, not only as prose buried in the task agent's prompt.

**Alternatives:** Only mention "no context found" inline in the task agent's prompt; treat an unexpected empty discovery result as an immediate hard failure with a new failure category.

**Rationale:** A scaffold-type task finding no existing code is normal, not a problem — the reviewer needs to know which case it is rather than guessing. Embedding the signal only as prose risks the Review Agent failing to notice it inside a longer context block. A structured field guarantees it factors into the verdict (e.g., extra scrutiny on whether the implementation assumes context it never saw). This reuses the existing Review Agent / retry loop rather than inventing a new failure category — bad output caused by missing context is still just bad output, caught the normal way.

**Tradeoff:** Adds one more field to the data passed from Task Executor to Review Agent. Minor schema growth, no new control flow.

---

### Impacted-files detection dropped

**Decision:** The structural "files that import a changed/ranked file" detection (`impacted_files` in the old `ContextPack`) is dropped entirely. It is not reimplemented in `FileIndexService` or anywhere else.

**Alternatives:** Keep a lightweight grep-based version instead of the full graph-based one.

**Rationale:** Well-designed code shouldn't cascade-impact importers for purely internal changes — if an interface genuinely changes in a way that affects callers, that's an intentional change the task description and the Code Discovery Agent's own navigation are better positioned to surface than a blanket structural signal. In practice the graph-based version was mostly noise (e.g., flagging every importer of a widely-used utility module regardless of relevance).

**Tradeoff:** A genuine cross-file ripple effect from a careless edit may go unnoticed by the discovery/review pipeline until CI or tests catch it, rather than being flagged proactively. Acceptable given the noise-to-signal ratio observed in practice.

---

### No orchestrator file tree (superseded — see "Orchestrator receives a repo map, not a file tree")

**Decision:** The orchestrator does not receive a file tree or any file contents.

**Alternatives:** Provide the orchestrator with a directory listing so it can reference files when decomposing tasks.

**Rationale:** The orchestrator's job is decomposing objectives into tasks — reasoning about what work needs to be done, not where code lives. File discovery is the Code Discoverer's job. Including a file tree in the orchestrator's context adds tokens on every loop iteration without providing value for task decomposition.

**Tradeoff:** The orchestrator cannot check whether a module already exists before creating a task to scaffold it. If this becomes a practical problem (duplicate file creation), the orchestrator can be given a tool call to check file existence on demand — not a file tree loaded into context by default.

**Superseded:** A live dogfood run showed the real cost of this: the orchestrator wrote a task requiring `on_task_complete` to color "blocked" task lines, unaware that blocked tasks structurally never reach that callback — 8 failed attempts across two issues before a human caught it. Zero codebase awareness turned out to make bad, contradictory task specs cheap to write and expensive to discover. See the new decision below for what replaced this.

---

### Orchestrator receives a repo map, not a file tree

**Decision:** The orchestrator is given a deterministically-assembled "repo map" — the concatenated `agent.md` index tree (per-directory one-line summaries plus top-level symbol/line-range listings), not raw source code and not a live navigation tool. Built by `FileIndexService.read_repo_map()`, capped at a small token budget (`ORCHESTRATOR_REPO_MAP_TOKEN_BUDGET`), root-first so truncation drops the least-central directories before the broad summary.

**Alternatives:** Keep the orchestrator fully blind (status quo, see superseded decision above); give it the same agentic `read_agent_md`/`list_subdirectories` tool-calling loop `CodeDiscoveryAgent` uses so it can navigate on demand.

**Rationale:** `agent.md` is already the cheap, deliberately-summarized layer this system produces for exactly this kind of low-cost awareness — reusing it costs a small, bounded slice of the orchestrator's existing context budget (measured at ~5,900 tokens for this repo's full tree at the time this was written), not a new per-call agentic loop. Since the repo map's content doesn't depend on which specific task is being planned, there's nothing for an agentic tool loop to decide — a static, deterministic assembly is cheaper and simpler than giving the orchestrator its own tool-calling turn.

**Tradeoff:** This only helps the orchestrator avoid contradictions visible at the *structural* level (a symbol/one-line summary). It does not give it deep cross-file behavioral/data-flow awareness — confirmed live: a follow-up task still required the same impossible `on_task_complete`/blocked-status behavior, because the fact that makes it impossible ("blocked tasks bypass this callback entirely") isn't the kind of thing a one-line symbol summary conveys. See "Reviewer may flag acceptance criteria as architecturally infeasible" below for how that specific gap is actually handled. Also inherits the pre-existing risk that `agent.md` can go stale relative to the real code (a separate, still-unaddressed problem) — the orchestrator's plans are only as good as the last `haive index` run.

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

### Reviewer may request specific files beyond task scope (superseded — see "Shared read_file tool replaces the reviewer's JSON-shape request protocol")

**Decision:** `ReviewAgent` can respond with `{"action": "request_file", "path": "..."}` instead of a verdict when it needs to verify a claim not covered by the code it was shown, up to a token budget shared across the whole review (reusing `_REVIEW_CONTEXT_BUDGET`, not a separate arbitrary request count). It stays on `ModelClient.call()` (plain text), not the agentic `call_single()`/tools protocol `CodeDiscoveryAgent` uses.

**Alternatives:** Give the reviewer the full agentic tool-calling loop (`read_agent_md`/`list_subdirectories`) like `CodeDiscoveryAgent`; leave the reviewer scoped only to what discovery already found for the task (status quo before this).

**Rationale:** The reviewer's context (`loaded_sections`) is scoped by the task's own description, not by what's needed to *verify* a claim about behavior elsewhere in the codebase — this caused a real failure where the reviewer couldn't confirm whether a callback ever receives certain data, because the file that would prove it was never in scope. A lightweight JSON request/response protocol avoids rewriting the reviewer's existing model-escalation tests (which mock `.call()` directly) and avoids introducing a second calling convention into the class.

**Tradeoff:** The reviewer can only request files it can already name from something visible in front of it (an import, a call site) — it cannot browse the repo from scratch the way `CodeDiscoveryAgent` can. This fixes "confirm a lead I already have," not "find the answer when nothing in view points anywhere." If that proves insufficient, the next step is giving it the same navigation tools discovery uses — deliberately deferred to keep this change small.

**Superseded:** The tradeoffs accepted above (avoid rewriting model-escalation tests, avoid a second calling convention) turned out to cost more than they saved. `TaskExecutor`'s code-editing call site needed the identical capability — a code editor explicitly said "I only have the run function in context... please provide the full contents" but had no schema-legitimate way to ask, since `min_length=1` (added separately to stop empty submissions) closed off the only escape valve. Building this twice, plus discovering a *third* independent hand-rolled version in `AgentMdGenerationAgent`, confirmed the "avoid a second calling convention" tradeoff was backwards — the JSON-shape convention *was* the second, less reliable one. See the new decision below for what replaced it.

---

### Shared read_file tool replaces the reviewer's JSON-shape request protocol

**Decision:** `ReviewAgent` and `TaskExecutor` both use one shared `read_file` tool + tool-calling loop (`haive/execution/read_file_tool.py`), built on `ModelClient.call_single()`/real tool-calling — the same mechanism `CodeDiscoveryAgent` already used successfully. `ContextRequest` and the JSON-shape-sniffing it required are retired entirely.

**Alternatives:** Generalize the existing JSON-shape convention into a shared helper both agents call, without switching to real tool-calling; give `TaskExecutor` its own separate ad-hoc mechanism rather than sharing one with the reviewer.

**Rationale:** Real tool-calling removes an entire class of failure this session kept hitting — a model choosing the wrong JSON shape, or producing malformed output under an ambiguous convention (the same failure mode showed up as the empty-edit bug, the orchestrator JSON-extraction failures, and the reviewer's own request-parsing). The provider's own tool-calling API resolves "is this a tool call or a final answer?" unambiguously; no more guessing is needed. Sharing one implementation between both consumers (and designing it so `AgentMdGenerationAgent` could adopt it later) also removes duplicated path-safety and budget-truncation logic that had already been copied twice.

**Tradeoff:** Both `ReviewAgent.review()` and `TaskExecutor._run_inner()` needed their core LLM-calling mechanism changed from a simple prompt/system string pair to a `messages` list threaded across retries/model-escalation — a larger, more invasive change than either individual fix would have been alone, and it required rewriting most of both files' existing tests. Accepted because doing it once, shared, is cheaper than the three-separate-implementations problem it replaces.

---

### Reviewer may flag acceptance criteria as architecturally infeasible

**Decision:** `ReviewVerdict`/`ReviewAgentOutput` gain `infeasible: bool`, mutually exclusive with `passed`/`uncertain`. When set, `TaskExecutor` stops retrying immediately (no further tiers) instead of burning the rest of the tier ladder, and the orchestrator may create a recovery task on the next wave using the reviewer's stated reason — without waiting for a human comment first, unlike ordinary `needs_human_review` recovery. `lineage_depth < max_recovery_depth` still caps this exactly as it caps comment-gated recovery.

**Alternatives:** Leave `infeasible` unrepresented and rely on `uncertain`/generic `passed=false` (status quo); require a human comment before any recovery, infeasible or not.

**Rationale:** Confirmed live: a reviewer can correctly diagnose that a criterion is structurally impossible (not just poorly implemented) partway through the tier ladder, and the system had no way to act on that distinction — it kept escalating tiers and repeating doomed fixes. The reviewer's own reasoning, when specific, is as good a signal as a human restating the same thing in a comment.

**Tradeoff:** Relies on the reviewer model restricting `infeasible=true` to genuine structural impossibilities rather than using it to dodge hard-but-solvable review calls — a prompt-following risk no schema validator can fully enforce. Also doesn't stop the *orchestrator* from writing an infeasible spec in the first place (see the repo map decision above) — it only stops the executor from wasting retries once that happens.

---

### Bounded autonomous run loop (`max_waves_per_run`)

**Decision:** `haive run` loops automatically across waves (plan → execute → replan) within a single invocation, up to `Settings.max_waves_per_run` (default 2), instead of exiting after exactly one wave and requiring a human to re-invoke it. The orchestrator's two "nothing further to do" cases (empty output, recovery depth exceeded) now raise a dedicated `OrchestratorStalledError(RuntimeError)` instead of a plain `RuntimeError`, so the CLI can stop the loop cleanly and wait on a human rather than crashing.

**Alternatives:** Keep single-wave-per-invocation (status quo, and what `architecture_overview.md`/`project_overview.md` described as the v1 non-goal — deliberately revised alongside this decision, not silently); gate autonomous looping behind an opt-in flag instead of making it the default.

**Rationale:** Automatic recovery (repo map, infeasible-verdict recovery) only reduces human involvement if a human doesn't still have to manually re-run the command between every automatic recovery — otherwise the "automatic" part only saves retries within a task, not the operator's attention between waves. `max_waves_per_run` is a deliberately conservative cap "for now," not a permanent ceiling — meant to be raised once this proves reliable in practice.

**Tradeoff:** Reclassifying those two `RuntimeError`s to `OrchestratorStalledError` changes `haive run`'s exit code for those specific cases from 1 to 0 — intentional (they're expected pause points, not bugs), but worth remembering if any external automation watches `haive run`'s exit code to decide success vs. failure, since it will now see "genuinely stalled, waiting on a human" as a clean exit (0) rather than a failure (1).

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

---

### One dedicated branch per milestone, wired from the data model instead of local git state

**Decision:** `haive run` derives `project_branch` from `Project.project_branch` (already computed by `GitHubPMAdapter.get_project()` as `f"haive/project-{project_id}"`), created once via `GitHubVCSAdapter.ensure_branch()` and reused across every `haive run` invocation for that milestone. Every task branches off it and merges into it; only the final "project complete" PR — never auto-merged, always left for human review — touches `main`.

**Alternatives:** Keep deriving `project_branch` from `git branch --show-current` (status quo); run every task directly against `main` with no intermediate branch at all.

**Rationale:** `Project.project_branch` already existed in the data model but was never read anywhere — `cli.py`'s `run()` command derived `project_branch` from whatever was locally checked out instead. In practice this meant one ad-hoc branch (`step-23-cli`) silently became the shared project branch for three unrelated milestones over several weeks, and once that branch was finally merged and deleted, `project_branch` degraded to `"main"` itself — producing a PR from `main` to `main` that GitHub correctly rejected. Wiring up the branch the data model already defines gives one clean, reviewable PR per milestone, keeps `main` protected for the milestone's entire duration, and removes the failure class entirely (a fresh project branch is only ever compared against `main`, never against itself).

**Tradeoff:** `ensure_branch()` must never behave like `create_branch()` (used for disposable per-task branches, which force-resets local state via `git checkout -B`) — a project branch accumulates task merges across many `haive run` invocations for the same milestone, so resetting it would silently discard that history. `branch_has_new_commits()` (checked proactively before the final PR, via `compare().ahead_by`) also covers the case where a milestone's project branch, freshly created off `main`'s current tip, has nothing new yet — not just the specific bug that surfaced this.

---

### `run-all`: `due_on` for ordering, a description marker for per-milestone autonomy, no persistent process

**Decision:** `haive run-all` processes open milestones in one invocation, ordered by the native GitHub Milestone `due_on` field (milestones without one sort last, tiebroken by milestone number). A milestone's final PR (branch → `main`) auto-merges only if its description contains a `#Checkpoint: false` line, parsed by the same informal `_parse_checkpoint` regex used for the existing `#Milestone/#Goal/#Scope` template; absence of the marker defaults to `true` (gated). The moment `run-all` hits a milestone that is done-but-gated, or not done (wave limit, stall, dry-run), it stops and prints why, relying on a later re-invocation to continue — no polling loop or daemon.

**Alternatives:** A dedicated `build_order` field or separate ordering resource; a global "autonomous mode" flag with no per-milestone opt-out; a persistent process that polls GitHub until a gated PR is merged, then resumes automatically.

**Rationale:** `due_on` already exists on every GitHub Milestone, is editable in the GitHub UI with no new infrastructure, and milestone numbers alone can't be reordered when milestones are inserted or split after the fact. Task-level merging is already governed by `--no-merge`; extending autonomy to the milestone's *final* PR only (not task PRs) keeps the two concerns — "should this task's change land automatically" vs. "should this milestone's work land on `main` automatically" — orthogonal. Putting the flag in the description rather than a new field means every pre-existing milestone needs no retroactive edit (defaulting to the safe, gated behavior) and keeps the "structured text in the description" pattern the orchestrator already parses consistent. A persistent polling process would be a new operational mode (something to start, monitor, and kill) where `haive run`'s entire design so far has been short-lived and resumable by re-invocation — introducing a daemon here would be inconsistent with that shape for a problem re-invocation already solves.

**Tradeoff:** A long run of `#Checkpoint: false` milestones advances automatically up to `max_milestones_per_run` (default 3) before stopping regardless of gating, as a backstop against an unbounded single invocation. `run-all` cannot resume mid-wait on its own — the user must notice the gated PR and either merge it or re-run once they have, same as today's single-milestone `haive run` already requires for wave limits and stalls.
