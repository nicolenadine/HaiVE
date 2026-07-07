## Files

__init__.py — Package initialization for observability module
setup.py — OpenTelemetry tracer setup and LiteLLM instrumentation
  setup_observability (function) — 14-32 — Configures OTel tracing with Phoenix OTLP exporter and LiteLLM auto-instrumentation
spans.py — Context managers for OpenTelemetry distributed tracing spans
  task_span (function) — 20-30 — Span context manager for individual task execution with identity attributes
  run_span (function) — 34-38 — Span context manager for full haive run wrapping the CLI run loop
