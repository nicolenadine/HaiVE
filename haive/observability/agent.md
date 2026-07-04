## Files

__init__.py — Package initialization for observability module
setup.py — OTel tracing and LiteLLM auto-instrumentation configuration
  setup_observability (function) — 14-32 — Configure OpenTelemetry tracing and LiteLLM instrumentation with OTLP exporter
spans.py — Context managers for distributed tracing spans
  task_span (function) — 20-30 — Context manager for task execution span with task identity attributes
  run_span (function) — 34-38 — Context manager for full haive run span with project identity
