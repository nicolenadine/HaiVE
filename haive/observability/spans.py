from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from opentelemetry import trace
from opentelemetry.trace import Span

from haive.models.task import Task

_TRACER_NAME = "haive"


def _get_tracer() -> trace.Tracer:
    """Indirection point so tests can monkeypatch the tracer without touching the global OTel state."""
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def task_span(task: Task) -> Generator[Span, None, None]:
    """Span for a single task execution. Sets task identity attributes on entry.

    The caller sets result attributes (verdict.passed, agent.prompt_version,
    attempt.number, tier.name, tier.model_used) on the yielded span.
    """
    with _get_tracer().start_as_current_span("task.run") as span:
        span.set_attribute("task.id", task.task_id)
        span.set_attribute("task.role", task.agent_role.value)
        span.set_attribute("task.complexity", task.complexity.value)
        yield span


@contextmanager
def run_span(project_id: str) -> Generator[Span, None, None]:
    """Span for a full haive run (one wave). Wraps the CLI run loop."""
    with _get_tracer().start_as_current_span("haive.run") as span:
        span.set_attribute("project.id", project_id)
        yield span
