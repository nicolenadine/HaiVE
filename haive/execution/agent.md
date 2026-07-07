## Files

context_assembler.py — Assembles user-facing context prompts from task descriptions, loaded code sections, dependencies, and feedback
  ContextAssembler (class) — 9-97 — Builds context prompts for task execution with task details, code sections, and retry feedback
  assemble (method) — 21-41 — Combines task, code context, dependencies, and feedback into a single prompt string
read_file_tool.py — Tool integration for LLMs to request repo files during execution with budget tracking and path safety
  READ_FILE_TOOL (constant) — 17-43 — OpenAI-compatible function schema for read_file tool
  read_file_for_tool_call (function) — 49-66 — Safely reads file content with token budgeting and truncation
  run_tool_loop (function) — 83-143 — Executes LLM tool-calling loop with file read support and budget management
output_validator.py — Validates and extracts JSON from LLM outputs against role-specific schemas
  OutputValidationError (class) — 21-27 — Exception for schema validation failures on agent output
  OutputValidator (class) — 46-113 — Parses and validates raw LLM output against registered agent role schemas
  validate (method) — 49-61 — Extracts and validates JSON output against the schema for a given agent role
  extract_json (method) — 64-113 — Finds JSON object in raw text via bare object, markdown fence, or brace scanning
review_agent.py — LLM-as-judge that evaluates task agent outputs against acceptance criteria with escalation
  ReviewAgent (class) — 34-198 — Validates agent output, reads original files, and performs multi-tier review with on-demand file access
  review (method) — 59-103 — Reviews agent output against criteria, escalating through REVIEWER_MODELS on uncertainty
  _build_prompt (method) — 128-184 — Constructs detailed review prompt with task, context, original files, and guidelines
task_executor.py — End-to-end task execution with branching, LLM calls, review, PR creation, and optional merge
  TaskExecutor (class) — 46-398 — Orchestrates task branching, code generation, review, and PR workflow
  run (method) — 76-102 — Executes task with observability span tracking
  _run_inner (method) — 104-283 — Main execution loop: tier ladder, discovery, LLM attempts, review, PR merge handling
  _finalize_success (method) — 287-363 — Applies output, pushes PR, reviews verdict, and optionally merges
  _check_for_catastrophic_deletion (function) — 403-430 — Detects destructive edits that drop significant file content
  _apply_output (function) — 433-442 — Writes agent output files to disk
__init__.py — Package initialization for execution module (empty or re-exports)
