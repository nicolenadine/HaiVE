## Files

__init__.py — Package initialization for execution module
context_assembler.py — Builds user-facing context prompts from task, code sections, dependencies, and feedback
  ContextAssembler (class) — 11-100 — Assembles task description, relevant code, dependencies, and retry feedback into a single prompt
output_validator.py — Validates raw LLM output against agent-specific JSON schemas
  OutputValidationError (class) — 8-16 — Raised when agent output fails parsing or schema validation
  OutputValidator (class) — 48-99 — Extracts and validates JSON output against role-specific Pydantic schemas
review_agent.py — LLM-as-judge evaluating task output against acceptance criteria with optional context expansion
  ReviewAgent (class) — 27-285 — Iterates through reviewer models, validates output, handles dynamic file requests
task_executor.py — Orchestrates full task execution: discovery, LLM calls, review, and PR creation
  TaskExecutor (class) — 40-324 — Executes task end-to-end with retry logic across complexity tiers
