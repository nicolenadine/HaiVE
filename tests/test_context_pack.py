from __future__ import annotations

from pathlib import Path

import pytest

from haive.models.context import ContextPack
from haive.models.enums import AgentRole, Complexity, TaskStatus
from haive.models.task import Task
from haive.repomap.db import RepoMapDB
from haive.repomap.graph import GraphBuilder
from haive.repomap.repo_map_service import RepoMapService

_MODULE_A = """\
import os
from pathlib import Path

def helper(x):
    return x * 2

class ServiceA:
    def __init__(self):
        pass

    def run(self, value):
        return helper(value)
"""

_MODULE_B = """\
from module_a import ServiceA

class ClientB:
    def execute(self):
        svc = ServiceA()
        return svc.run(42)
"""

_MODULE_C = """\
def standalone():
    pass
"""


def _make_task(title: str = "Use ServiceA", description: str = "Implement ServiceA usage") -> Task:
    return Task(
        task_id="1",
        title=title,
        description=description,
        agent_role=AgentRole.CODE_EDITOR_AGENT,
        complexity=Complexity.MEDIUM,
        depends_on=[],
        acceptance_criteria=["It works"],
        status=TaskStatus.PENDING,
    )


def _setup(tmp_path: Path) -> tuple[RepoMapService, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module_a.py").write_text(_MODULE_A)
    (repo / "module_b.py").write_text(_MODULE_B)
    (repo / "module_c.py").write_text(_MODULE_C)
    db = RepoMapDB.initialize(":memory:")
    svc = RepoMapService(db, str(repo))
    svc.scan_repo(str(repo))
    GraphBuilder().build_edges(db)
    return svc, repo


class TestContextPackBasics:
    def test_token_estimate_is_non_negative(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert pack.token_estimate >= 0

    def test_token_estimate_within_budget(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=500)
        assert pack.token_estimate <= 500

    def test_very_tight_budget_trims_all_symbols(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=1)
        assert pack.token_estimate <= 1

    def test_relevant_files_non_empty_for_matching_query(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert len(pack.relevant_files) > 0

    def test_relevant_files_paths_are_strings(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert all(isinstance(f.path, str) for f in pack.relevant_files)

    def test_returns_context_pack_instance(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert isinstance(pack, ContextPack)


class TestContextPackSymbols:
    def test_symbols_trimmed_lowest_ranked_first(self, tmp_path):
        svc, _ = _setup(tmp_path)
        full_pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        tight_pack = svc.get_context_pack(_make_task(), token_budget=10)
        if full_pack.relevant_symbols and tight_pack.relevant_symbols:
            # first symbol in tight pack must be from the highest-ranked file
            assert tight_pack.relevant_symbols[0].file_path == full_pack.relevant_symbols[0].file_path

    def test_symbol_source_is_non_empty(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert all(s.source for s in pack.relevant_symbols)

    def test_symbol_source_contains_def(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        sources = "\n".join(s.source for s in pack.relevant_symbols)
        assert "def " in sources or "class " in sources

    def test_symbol_line_numbers_are_positive(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        assert all(s.start_line >= 1 and s.end_line >= s.start_line for s in pack.relevant_symbols)


class TestContextPackBrokenReferences:
    def test_broken_references_populated_for_unresolved_imports(self, tmp_path):
        # module_a imports os and Path — neither is defined in our files
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(
            _make_task(title="ServiceA", description="ServiceA implementation"),
            token_budget=10_000,
        )
        broken_names = {br.symbol_name for br in pack.broken_references}
        assert "os" in broken_names or "Path" in broken_names

    def test_broken_reference_has_file_path_and_line(self, tmp_path):
        svc, _ = _setup(tmp_path)
        pack = svc.get_context_pack(_make_task(), token_budget=10_000)
        for br in pack.broken_references:
            assert br.file_path
            assert br.line_number >= 1


class TestContextPackImpactedFiles:
    def test_impacted_files_lists_importer_of_ranked_file(self, tmp_path):
        svc, _ = _setup(tmp_path)
        # module_a defines ServiceA (will be top-ranked); module_b imports it
        pack = svc.get_context_pack(
            _make_task(title="ServiceA", description="ServiceA implementation"),
            token_budget=10_000,
        )
        ranked_paths = {f.path for f in pack.relevant_files}
        # if module_a is ranked and module_b is not, module_b should appear in impacted_files
        if any("module_a" in p for p in ranked_paths) and not any("module_b" in p for p in ranked_paths):
            assert any("module_b" in p for p in pack.impacted_files)
