## Files

__init__.py — Package initialization for observability module
setup.py — OpenTelemetry and LiteLLM instrumentation configuration
  setup_observability (function) — 14-32 — Configures OTel tracing and LiteLLM auto-instrumentation to export spans to Phoenix
spans.py — Distributed tracing context managers for task and run execution
  task_span (function) — 19-28 — Context manager that creates a span for single task execution with task identity attributes
  run_span (function) — 31-37 — Context manager that creates a span for full haive run wrapping the CLI loop
