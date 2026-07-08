## Files

__init__.py — Package initialization for orchestration module
example_library.py — Load and manage orchestrator planning examples from YAML
  ExampleTaskPattern (class) — 10-16 — Task pattern with agent role, complexity, and dependencies
  ExampleMiniTask (class) — 19-25 — Minimal task representation for example mini-milestones
  ExampleMiniMilestone (class) — 28-32 — Mini-milestone with example tasks
  OrchestratorExample (class) — 35-55 — Full planning example with patterns and guidance
  OrchestratorExampleLibrary (class) — 58-70 — Validated collection of orchestrator examples
  ExampleLibrary (class) — 73-111 — Runtime manager for loading and accessing examples by ID
  format_examples_for_prompt (function) — 114-166 — Format examples into readable sections for LLM prompt
example_selector.py — Select relevant examples based on milestone tags and keywords
  ExampleSelector (class) — 97-116 — Select top-N planning examples matching milestone text
  classify_tags (function) — 72-83 — Extract positive and excluded tags from milestone text
  score_example (function) — 86-94 — Score example relevance based on tag overlap
example_tags.py — Tag definitions and scoring weights for example selection
  KNOWN_TAGS (constant) — 3-17 — Set of valid example tags
examples.yaml — YAML library of orchestrator planning examples with patterns and mini-examples
orchestrator.py — LLM-based orchestrator for decomposing milestones into tasks
  Orchestrator (class) — 26-87 — Creates task waves via LLM prompt with example selection
  OrchestratorStalledError (class) — 17-23 — Exception for orchestrator safety constraints
orchestrator_prompt.py — System prompt template for orchestrator LLM execution
  build_orchestrator_prompt (function) — 3-178 — Build task decomposition prompt with rules and examples
task_scheduler.py — Concurrent task execution scheduler respecting dependencies
  TaskScheduler (class) — 13-125 — Schedule and run tasks concurrently with dependency ordering
task_view_builder.py — Build OrchestratorTaskView from task state for LLM context
  TaskViewBuilder (class) — 12-60 — Convert tasks to views with token budget management
