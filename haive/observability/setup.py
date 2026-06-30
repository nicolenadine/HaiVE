from __future__ import annotations

from openinference.instrumentation.litellm import LiteLLMInstrumentor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from haive.models.config import Settings

_initialized = False


def setup_observability(settings: Settings) -> None:
    """Configure OTel tracing and LiteLLM auto-instrumentation.

    Idempotent — safe to call multiple times (subsequent calls are no-ops).
    The export target is controlled by `settings.phoenix_otlp_endpoint`
    (env var PHOENIX_OTLP_ENDPOINT).
    """
    global _initialized
    if _initialized:
        return

    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=settings.phoenix_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    LiteLLMInstrumentor().instrument()

    _initialized = True
