## Files

__init__.py — Empty package initialization
example_library.py — Pydantic models and library for orchestrator planning examples
  ExampleTaskPattern (class) — 8-14 — Agent role, purpose, complexity, and dependencies for a single step
  ExampleMiniTask (class) — 17-23 — Simplified task representation used in mini-examples
  ExampleMiniMilestone (class) — 26-30 — Container for milestone title and expected tasks in an example
  OrchestratorExample (class) — 33-55 — Complete planning pattern with tags, use-cases, task graph, and mini-example
  OrchestratorExampleLibrary (class) — 58-68 — Validated collection of orchestrator examples
  ExampleLibrary (class) — 71-106 — Runtime library managing examples by ID with YAML loading
  format_examples_for_prompt (function) — 109-159 — Formats selected examples into a structured prompt section
example_selector.py — Scoring and selection of relevant planning examples based on milestone tags
  ExampleSelector (class) — 74-88 — Selects top-K examples matching milestone text via keyword and tag scoring
example_tags.py — Definition and scoring of planning example tags
  KNOWN_TAGS (constant) — 3-17 — Frozenset of all valid example tag names
examples.yaml — YAML data file with 10 planning patterns for milestone decomposition
orchestrator.py — Main orchestrator loop calling LLM and validating task graph output
  Orchestrator (class) — 25-84 — Runs planning loop with example selection, LLM call, and recovery depth validation
orchestrator_prompt.py — System prompt builder for orchestrator LLM calls
  build_orchestrator_prompt (function) — 4-130 — Constructs detailed system prompt with rules, schemas, and optional planning examples
task_scheduler.py — Concurrent task execution with dependency ordering and failure handling
  TaskScheduler (class) — 7-127 — Schedules up to 2 concurrent tasks respecting dependencies and blocking on failures
task_view_builder.py — Converts tasks to orchestrator-safe views with token budget trimming
  TaskViewBuilder (class) — 11-49 — Builds task views and prunes completed tasks to fit token budget
