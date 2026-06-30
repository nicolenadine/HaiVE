from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task
from haive.observability.spans import run_span, task_span


# ── helpers ───────────────────────────────────────────────────────────────────

def make_task(**kwargs) -> Task:
    defaults = dict(
        task_id="42",
        title="Add retry logic",
        description="Wrap HTTP calls.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.LOW,
        depends_on=[],
        acceptance_criteria=[],
        status=TaskStatus.PENDING,
    )
    return Task(**(defaults | kwargs))


def make_test_tracer() -> tuple[InMemorySpanExporter, object]:
    """Return (exporter, tracer) backed by an isolated in-memory TracerProvider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("haive")
    return exporter, tracer


# ── setup_observability ───────────────────────────────────────────────────────

class TestSetupObservability:
    """Tests that setup_observability wires OTel without touching global state in CI."""

    def _make_settings(self):
        from haive.models.config import Settings
        return Settings(
            _env_file=None,
            pm_adapter="github",
            vcs_adapter="github",
            github_token="tok",
            github_repo="owner/repo",
            github_project_id=1,
        )

    def _patch_setup(self, monkeypatch, setup_module, *, mock_trace=None, mock_exporter_cls=None):
        """Patch all external OTel calls in setup.py to avoid global state mutations."""
        _noop = lambda *a, **kw: MagicMock()
        monkeypatch.setattr(setup_module, "_initialized", False)
        monkeypatch.setattr(setup_module, "trace", mock_trace or MagicMock())
        monkeypatch.setattr(setup_module, "LiteLLMInstrumentor", lambda: MagicMock())
        monkeypatch.setattr(setup_module, "TracerProvider", lambda: MagicMock())
        monkeypatch.setattr(setup_module, "OTLPSpanExporter", mock_exporter_cls or _noop)
        monkeypatch.setattr(setup_module, "BatchSpanProcessor", _noop)

    def test_setup_does_not_raise(self, monkeypatch):
        import haive.observability.setup as setup_module
        self._patch_setup(monkeypatch, setup_module)
        setup_module.setup_observability(self._make_settings())

    def test_setup_is_idempotent(self, monkeypatch):
        import haive.observability.setup as setup_module
        mock_trace = MagicMock()
        self._patch_setup(monkeypatch, setup_module, mock_trace=mock_trace)

        s = self._make_settings()
        setup_module.setup_observability(s)
        setup_module.setup_observability(s)

        # Provider set exactly once despite two calls
        assert mock_trace.set_tracer_provider.call_count == 1

    def test_endpoint_comes_from_settings(self, monkeypatch):
        import haive.observability.setup as setup_module
        captured_endpoint: list[str] = []

        def mock_exporter(*, endpoint: str) -> MagicMock:
            captured_endpoint.append(endpoint)
            return MagicMock()

        self._patch_setup(monkeypatch, setup_module, mock_exporter_cls=mock_exporter)
        settings = self._make_settings()
        settings.phoenix_otlp_endpoint = "http://my-phoenix:9999/v1/traces"
        setup_module.setup_observability(settings)

        assert captured_endpoint == ["http://my-phoenix:9999/v1/traces"]


# ── task_span ─────────────────────────────────────────────────────────────────

class TestTaskSpan:
    """Tests use monkeypatching to inject an in-memory tracer — avoids touching global OTel state."""

    def test_emits_span_with_task_attributes(self, monkeypatch):
        import haive.observability.spans as spans_module
        exporter, tracer = make_test_tracer()
        monkeypatch.setattr(spans_module, "_get_tracer", lambda: tracer)

        with task_span(make_task()):
            pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["task.id"] == "42"
        assert attrs["task.role"] == "implementation_agent"
        assert attrs["task.complexity"] == "low"

    def test_span_name_is_task_run(self, monkeypatch):
        import haive.observability.spans as spans_module
        exporter, tracer = make_test_tracer()
        monkeypatch.setattr(spans_module, "_get_tracer", lambda: tracer)

        with task_span(make_task()):
            pass

        assert exporter.get_finished_spans()[0].name == "task.run"

    def test_caller_can_set_additional_attributes(self, monkeypatch):
        import haive.observability.spans as spans_module
        exporter, tracer = make_test_tracer()
        monkeypatch.setattr(spans_module, "_get_tracer", lambda: tracer)

        with task_span(make_task()) as span:
            span.set_attribute("verdict.passed", True)
            span.set_attribute("attempt.number", 1)

        attrs = exporter.get_finished_spans()[0].attributes
        assert attrs["verdict.passed"] is True
        assert attrs["attempt.number"] == 1

    def test_task_role_and_complexity_reflect_task_values(self, monkeypatch):
        import haive.observability.spans as spans_module
        exporter, tracer = make_test_tracer()
        monkeypatch.setattr(spans_module, "_get_tracer", lambda: tracer)

        with task_span(make_task(agent_role=AgentRole.SCAFFOLD_AGENT, complexity=Complexity.HIGH)):
            pass

        attrs = exporter.get_finished_spans()[0].attributes
        assert attrs["task.role"] == "scaffold_agent"
        assert attrs["task.complexity"] == "high"


# ── run_span ──────────────────────────────────────────────────────────────────

class TestRunSpan:
    def test_emits_span_with_project_id(self, monkeypatch):
        import haive.observability.spans as spans_module
        exporter, tracer = make_test_tracer()
        monkeypatch.setattr(spans_module, "_get_tracer", lambda: tracer)

        with run_span("proj-123"):
            pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "haive.run"
        assert spans[0].attributes["project.id"] == "proj-123"
