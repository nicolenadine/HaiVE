## Files

__init__.py — Module exports for execution orchestration
context_assembler.py — Builds user-facing context prompts from discovered code and task details
  ContextAssembler (class) — 9-97 — Assembles task description, code context, dependency outputs, and retry feedback into a complete prompt
output_validator.py — Validates and extracts JSON output from LLM responses against agent schemas
  OutputValidator (class) — 46-88 — Extracts and validates JSON from raw LLM output against registered agent role schemas
  OutputValidationError (class) — 21-27 — Exception raised when agent output cannot be parsed or validated
review_agent.py — LLM-as-judge for evaluating task agent output against acceptance criteria
  ReviewAgent (class) — 36-232 — Reviews agent output with model escalation and on-demand file context requests
task_executor.py — End-to-end task execution orchestration from discovery through PR merge
  TaskExecutor (class) — 36-365 — Executes tasks with tier ladder, context discovery, validation, and review loop
