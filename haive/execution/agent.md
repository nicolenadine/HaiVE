## Files

__init__.py — Package initialization for haive execution module
context_assembler.py — Assembles user-facing context prompts from pre-loaded pieces
  ContextAssembler (class) — 9-97 — Builds multi-section context from task, code sections, dependencies, and retry feedback
output_validator.py — Validates raw LLM output against agent-role-specific schemas
  OutputValidationError (class) — 21-27 — Exception raised when agent output fails parsing or validation
  OutputValidator (class) — 86-181 — Extracts and validates JSON from model output against schema map
  OutputValidator.validate (method) — 94-105 — Validates raw LLM output against schema for given agent role
  OutputValidator.extract_json (method) — 107-172 — Locates JSON in raw text with brace-balance tracking and markdown fence preference
read_file_tool.py — Tool loop for agentic models with on-demand file reading capability
  ToolLoopResult (class) — 42-46 — Result dataclass containing model content, model name, messages, and remaining budget
  read_file_for_tool_call (function) — 49-66 — Safely reads repo file with path validation, token counting, and budget enforcement
  run_tool_loop (function) — 92-166 — Executes model call loop honoring read_file tool requests within token and round budgets
review_agent.py — LLM-as-judge evaluating task output against acceptance criteria
  ReviewAgent (class) — 34-198 — Escalates through reviewer model tiers on uncertain verdicts, reads files on demand for verification
  ReviewAgent.review (method) — 57-98 — Evaluates agent output and returns ReviewVerdict with pass/fail/uncertain states
task_executor.py — End-to-end task execution: discovery, LLM, review, PR creation, and merge
  TaskExecutor (class) — 46-410 — Orchestrates task execution with tiered LLM attempts, review, and VCS integration
  TaskExecutor.run (method) — 76-97 — Entry point wrapping execution with observability span and attribute tracking
  _check_for_catastrophic_deletion (function) — 415-442 — Detects suspicious full-file edits that drop >50% of original content
