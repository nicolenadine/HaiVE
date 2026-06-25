from __future__ import annotations

from haive.execution.context_assembler import ContextAssembler
from haive.models.config import AgentConfig
from haive.models.context import (
    BrokenReference,
    ContextPack,
    RelevantFile,
    RelevantSymbol,
)
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task


def _make_task(
    depends_on: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
) -> Task:
    return Task(
        task_id="t0",
        title="Implement login endpoint",
        description="Add POST /login that returns a JWT.",
        agent_role=AgentRole.IMPLEMENTATION_AGENT,
        complexity=Complexity.MEDIUM,
        depends_on=depends_on or [],
        acceptance_criteria=acceptance_criteria or ["Returns 200 on valid credentials"],
        status=TaskStatus.PENDING,
    )


def _make_symbol(
    qualified_name: str = "auth.login",
    source: str = "def login(user, pw):\n    pass",
    file_path: str = "auth.py",
) -> RelevantSymbol:
    return RelevantSymbol(
        qualified_name=qualified_name,
        kind="function",
        file_path=file_path,
        start_line=1,
        end_line=2,
        source=source,
    )


def _make_context_pack(
    symbols: list[RelevantSymbol] | None = None,
    files: list[RelevantFile] | None = None,
    impacted: list[str] | None = None,
    broken: list[BrokenReference] | None = None,
) -> ContextPack:
    return ContextPack(
        relevant_symbols=symbols if symbols is not None else [_make_symbol()],
        relevant_files=files if files is not None else [RelevantFile(path="auth.py", reason="defines 'login'")],
        impacted_files=impacted if impacted is not None else ["app.py"],
        broken_references=broken if broken is not None else [],
        symbol_source_token_estimate=10,
    )


def _make_agent_config() -> AgentConfig:
    return AgentConfig(
        role=AgentRole.IMPLEMENTATION_AGENT,
        description="Writes new code to implement features.",
        skills=["write functions", "add classes"],
        system_prompt="prompts/implementation_agent.md",
        output_schema="schemas/implementation_output.json",
        max_tokens=4096,
        retry_limit=2,
        prompt_version="1.0",
    )


def _assemble(**kwargs) -> str:
    defaults = dict(
        task=_make_task(),
        context_pack=_make_context_pack(),
        agent_config=_make_agent_config(),
        dependency_outputs={},
        retry_feedback=None,
    )
    defaults.update(kwargs)
    return ContextAssembler().assemble_prompt(**defaults)


class TestSectionPresence:
    def test_task_title_present(self):
        result = _assemble()
        assert "Implement login endpoint" in result

    def test_task_description_present(self):
        result = _assemble()
        assert "Add POST /login" in result

    def test_acceptance_criteria_listed(self):
        task = _make_task(acceptance_criteria=["Returns 200", "Returns 401"])
        result = _assemble(task=task)
        assert "Returns 200" in result
        assert "Returns 401" in result

    def test_relevant_code_present(self):
        sym = _make_symbol(qualified_name="auth.login", source="def login(): pass")
        result = _assemble(context_pack=_make_context_pack(symbols=[sym]))
        assert "auth.login" in result
        assert "def login(): pass" in result

    def test_relevant_files_listed(self):
        files = [
            RelevantFile(path="auth.py", reason="defines 'login'"),
            RelevantFile(path="models.py", reason="defines 'User'"),
        ]
        result = _assemble(context_pack=_make_context_pack(files=files))
        assert "auth.py" in result
        assert "models.py" in result

    def test_impacted_files_listed(self):
        result = _assemble(context_pack=_make_context_pack(impacted=["app.py", "routes.py"]))
        assert "app.py" in result
        assert "routes.py" in result


class TestSectionOrder:
    def test_section_order(self):
        result = _assemble(
            task=_make_task(depends_on=["t1"]),
            dependency_outputs={"t1": "output text"},
        )
        assert result.index("## Task") < result.index("## Acceptance Criteria")
        assert result.index("## Acceptance Criteria") < result.index("## Relevant Code")
        assert result.index("## Relevant Code") < result.index("## Relevant Files")
        assert result.index("## Relevant Files") < result.index("## Dependency Outputs")


class TestConditionalSections:
    def test_no_feedback_section_on_first_attempt(self):
        result = _assemble(retry_feedback=None)
        assert "Feedback from Previous Attempt" not in result

    def test_empty_feedback_list_produces_no_section(self):
        result = _assemble(retry_feedback=[])
        assert "Feedback from Previous Attempt" not in result

    def test_feedback_section_present_on_retry(self):
        result = _assemble(retry_feedback=["fix X", "fix Y"])
        assert "fix X" in result
        assert "fix Y" in result

    def test_feedback_section_is_last(self):
        result = _assemble(
            task=_make_task(depends_on=["t1"]),
            dependency_outputs={"t1": "dep output"},
            retry_feedback=["fix Z"],
        )
        assert result.index("Feedback from Previous Attempt") > result.index("Dependency Outputs")

    def test_empty_impacted_files_omits_section(self):
        result = _assemble(context_pack=_make_context_pack(impacted=[]))
        assert "Impacted Files" not in result

    def test_empty_relevant_symbols_omits_code_section(self):
        result = _assemble(context_pack=_make_context_pack(symbols=[]))
        assert "Relevant Code" not in result

    def test_empty_broken_references_omits_section(self):
        result = _assemble(context_pack=_make_context_pack(broken=[]))
        assert "Broken References" not in result

    def test_broken_references_section_present_when_populated(self):
        br = BrokenReference(file_path="app.py", symbol_name="missing_fn", line_number=42)
        result = _assemble(context_pack=_make_context_pack(broken=[br]))
        assert "Broken References" in result
        assert "missing_fn" in result
        assert "app.py:42" in result


class TestDependencyOutputs:
    def test_dependency_outputs_in_depends_on_order(self):
        task = _make_task(depends_on=["t1", "t2"])
        result = _assemble(
            task=task,
            dependency_outputs={"t1": "first output", "t2": "second output"},
        )
        assert result.index("first output") < result.index("second output")

    def test_missing_dependency_output_is_skipped(self):
        task = _make_task(depends_on=["t1", "t2"])
        result = _assemble(task=task, dependency_outputs={"t1": "only t1"})
        assert "only t1" in result
        assert "t2" not in result

    def test_no_dependency_section_when_empty(self):
        result = _assemble(dependency_outputs={})
        assert "Dependency Outputs" not in result

    def test_no_dependency_section_when_no_depends_on_matches(self):
        task = _make_task(depends_on=["t99"])
        result = _assemble(task=task, dependency_outputs={"t1": "irrelevant"})
        assert "Dependency Outputs" not in result


class TestBrokenReferences:
    def test_broken_references_listed(self):
        br = BrokenReference(file_path="svc.py", symbol_name="unknown_func", line_number=7)
        result = _assemble(context_pack=_make_context_pack(broken=[br]))
        assert "unknown_func" in result
        assert "svc.py:7" in result

    def test_no_broken_references_section_when_empty(self):
        result = _assemble(context_pack=_make_context_pack(broken=[]))
        assert "Broken References" not in result
