## Files

__init__.py — Empty module initialization
example_library.py — Pydantic models and loader for orchestrator planning examples
  ExampleTaskPattern (class) — 10-16 — Task pattern with agent role, purpose, and dependencies
  ExampleMiniTask (class) — 19-25 — Mini example task for documentation and reference
  ExampleMiniMilestone (class) — 28-32 — Container for milestone title and expected tasks
  OrchestratorExample (class) — 35-55 — Complete example with patterns, tags, and mini demonstrations
  OrchestratorExampleLibrary (class) — 58-70 — Validated collection of orchestrator examples
  ExampleLibrary (class) — 73-111 — In-memory example library with ID-based lookup and YAML file loading
  format_examples_for_prompt (function) — 114-166 — Formats selected examples into prompt text with patterns and guidance
example_selector.py — Tag-based selection of orchestrator examples matching milestone requirements
  ExampleSelector (class) — 97-116 — Selects relevant examples from library using keyword matching and scoring
example_tags.py — Known tags and scoring rules for example selection classification
  KNOWN_TAGS (constant) — 3-16 — Frozenset of 14 valid example classification tags
orchestrator.py — Main orchestrator that decomposes milestones into tasks with AI assistance
  OrchestratorStalledError (class) — 18-24 — Raised when orchestrator cannot proceed with automatic action
  Orchestrator (class) — 37-96 — Decomposes milestones into tasks using LLM with example-based guidance and recovery logic
examples.yaml — Predefined planning examples for milestone decomposition across 10 common patterns
orchestrator_prompt.py — System prompt template for orchestrator LLM with task decomposition rules
  build_orchestrator_prompt (function) — 3-174 — Builds orchestrator system prompt with decomposition rules and recovery logic
task_scheduler.py — Concurrent task execution scheduler respecting dependency constraints
  TaskScheduler (class) — 13-122 — Manages parallel task execution with MAX_EXECUTORS=2, dependency ordering, and automatic blocking of downstream tasks
task_view_builder.py — Converts tasks and execution state into compact orchestrator-ready views
  TaskViewBuilder (class) — 12-60 — Builds task views with token budgeting to remove complete tasks when exceeding context limit
