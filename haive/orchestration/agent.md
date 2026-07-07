## Files

__init__.py — Package initialization for orchestration module
example_library.py — Pydantic models and loader for orchestrator example patterns
  ExampleTaskPattern (class) — 10-16 — Task pattern with agent role, purpose, and complexity
  ExampleMiniTask (class) — 19-25 — Minimal task representation with agent and dependencies
  ExampleMiniMilestone (class) — 28-32 — Milestone container with expected task list
  OrchestratorExample (class) — 35-55 — Complete example with pattern, tags, use cases, and mini example
  OrchestratorExampleLibrary (class) — 58-70 — Validated collection of examples with duplicate checking
  ExampleLibrary (class) — 73-111 — Runtime library for loading and querying examples from YAML
  format_examples_for_prompt (function) — 114-166 — Formats selected examples into readable prompt text
example_selector.py — Tag-based example selection using keyword matching and scoring
  classify_tags (function) — 72-83 — Extracts positive and excluded tags from milestone text
  score_example (function) — 86-94 — Scores example match by tag overlap and penalties
  ExampleSelector (class) — 97-116 — Selects top-N relevant examples for a milestone
example_tags.py — Known tags and tag classification configuration for example selection
  KNOWN_TAGS (constant) — 3-17 — Frozenset of valid tag names for orchestrator examples
examples.yaml — YAML library of planning patterns and example task decompositions for milestones
orchestrator.py — Main orchestrator loop orchestrating task planning and recovery decisions
  OrchestratorStalledError (class) — 18-24 — Exception for safety mechanisms preventing infinite loops
  Orchestrator (class) — 37-96 — Runs planning loop with LLM, example selection, and recovery validation
orchestrator_prompt.py — Prompt template generation for the orchestrator LLM
  build_orchestrator_prompt (function) — 3-178 — Generates system prompt for task planning and recovery
task_scheduler.py — Concurrent task execution scheduler respecting dependency ordering
  TaskScheduler (class) — 13-125 — Schedules async task execution with dependency tracking and blocking
task_view_builder.py — Constructs task views for orchestrator context with token budgeting
  TaskViewBuilder (class) — 12-60 — Filters and compresses task history to fit context window
