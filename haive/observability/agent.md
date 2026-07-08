## Files

__init__.py — Package initializer for observability module
setup.py — OTel tracing and LiteLLM auto-instrumentation setup
  setup_observability (function) — 14-32 — Configures OpenTelemetry tracing with OTLP exporter and instruments LiteLLM
spans.py — Context managers for distributed tracing spans
  task_span (function) — 20-30 — Context manager for task execution spans with task identity attributes
  run_span (function) — 34-38 — Context manager for full haive run spans with project identity
