"""
Focused tests for tokenized keyword matching and personalized PageRank.
These complement the basic Ranker tests in test_repomap_graph.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from haive.repomap.db import RepoMapDB
from haive.repomap.graph import GraphBuilder, Ranker, _idf_weight, _tokenize_query
from haive.repomap.repo_map_service import RepoMapService

# --- file content fixtures ---

_CLI_PY = """\
def _resolve_milestone_id(cli_value):
    pass

def run():
    pass
"""

_CONFIG_MANAGER_PY = """\
class ConfigManager:
    def get_value(self, key):
        pass
"""

_RUNNER_PY = """\
def run():
    pass

def helper():
    pass
"""

_ENUMS_PY = """\
class TaskStatus:
    PENDING = 'pending'
    DONE = 'done'
"""

# These three import TaskStatus → give enums.py high in-degree
_ORCHESTRATOR_PY = """\
from enums import TaskStatus

class Orchestrator:
    pass
"""

_EXECUTOR_PY = """\
from enums import TaskStatus

class Executor:
    pass
"""

_SCHEDULER_PY = """\
from enums import TaskStatus

class Scheduler:
    pass
"""


def _setup(tmp_path: Path) -> RepoMapService:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "cli.py": _CLI_PY,
        "config_manager.py": _CONFIG_MANAGER_PY,
        "runner.py": _RUNNER_PY,
        "enums.py": _ENUMS_PY,
        "orchestrator.py": _ORCHESTRATOR_PY,
        "executor.py": _EXECUTOR_PY,
        "scheduler.py": _SCHEDULER_PY,
    }
    for name, content in files.items():
        (repo / name).write_text(content)
    db = RepoMapDB.initialize(":memory:")
    svc = RepoMapService(db, str(repo))
    svc.scan_repo(str(repo))
    GraphBuilder().build_edges(db)
    return svc


class TestTokenizeQuery:
    def test_splits_on_spaces_and_punctuation(self):
        result = _tokenize_query("fix the error-message now")
        assert "fix" in result
        assert "error" in result
        assert "message" in result
        assert "now" in result

    def test_filters_short_tokens(self):
        result = _tokenize_query("a to in fix")
        assert "a" not in result
        assert "to" not in result
        assert "in" not in result
        assert "fix" in result

    def test_preserves_underscored_identifiers(self):
        result = _tokenize_query("_resolve_milestone_id GITHUB_MILESTONE_ID")
        assert "_resolve_milestone_id" in result
        assert "github_milestone_id" in result

    def test_lowercases_tokens(self):
        result = _tokenize_query("ConfigManager TaskStatus")
        assert "configmanager" in result
        assert "taskstatus" in result

    def test_empty_query_returns_empty(self):
        assert _tokenize_query("") == []

    def test_query_with_only_short_words_returns_empty(self):
        assert _tokenize_query("a in to") == []


class TestIdfWeight:
    def test_lower_df_gives_higher_weight(self):
        assert _idf_weight(1) > _idf_weight(10)

    def test_weight_is_positive(self):
        assert _idf_weight(1) > 0
        assert _idf_weight(100) > 0

    def test_weight_decreases_with_df(self):
        weights = [_idf_weight(df) for df in [1, 5, 10, 50]]
        assert weights == sorted(weights, reverse=True)


class TestPersonalizedPageRank:
    def test_specific_symbol_match_surfaces_file(self, tmp_path):
        svc = _setup(tmp_path)
        # _resolve_milestone_id is unique to cli.py — should rank at the top
        results = Ranker().rank_files(svc._db, "_resolve_milestone_id", top_k=7)
        paths = [r.path for r in results]
        assert any("cli" in p for p in paths), f"cli.py not in results: {paths}"
        cli_rank = next(i for i, p in enumerate(paths) if "cli" in p)
        assert cli_rank == 0, f"cli.py should be #1, got rank {cli_rank}"

    def test_high_indegree_unmatched_file_demoted(self, tmp_path):
        svc = _setup(tmp_path)
        # enums.py has in-degree 3 (highest) but no match for this query
        # cli.py has in-degree 0 but defines the queried symbol
        results = Ranker().rank_files(
            svc._db,
            "Fix milestone resolution _resolve_milestone_id",
            top_k=7,
        )
        paths = [r.path for r in results]
        cli_rank = next((i for i, p in enumerate(paths) if "cli" in p), None)
        enums_rank = next((i for i, p in enumerate(paths) if "enums" in p), len(paths))
        assert cli_rank is not None, "cli.py not in results"
        assert cli_rank < enums_rank, (
            f"cli.py (rank {cli_rank}) should beat enums.py (rank {enums_rank})"
        )

    def test_no_keyword_match_falls_back_to_standard_pagerank(self, tmp_path):
        svc = _setup(tmp_path)
        # query that matches no symbol or path
        results = Ranker().rank_files(svc._db, "xyzzy_nonexistent_zzz", top_k=7)
        # enums.py has highest in-degree so should rank first under standard PR
        paths = [r.path for r in results]
        assert len(results) > 0
        assert all(r.score > 0 for r in results)
        enums_rank = next((i for i, p in enumerate(paths) if "enums" in p), None)
        assert enums_rank == 0, f"enums.py should be #1 under standard PR, got rank {enums_rank}"

    def test_unique_symbol_reason_names_symbol(self, tmp_path):
        svc = _setup(tmp_path)
        results = Ranker().rank_files(svc._db, "_resolve_milestone_id", top_k=1)
        assert len(results) == 1
        assert "_resolve_milestone_id" in results[0].reason

    def test_common_symbol_gets_lower_seed_weight_than_specific_one(self, tmp_path):
        svc = _setup(tmp_path)
        # `run` appears in both cli.py and runner.py (df=2)
        # `_resolve_milestone_id` appears in only cli.py (df=1)
        # cli.py should score higher than runner.py because it also matches the specific token
        results = Ranker().rank_files(
            svc._db, "_resolve_milestone_id run", top_k=7
        )
        paths = [r.path for r in results]
        cli_rank = next((i for i, p in enumerate(paths) if "cli" in p), None)
        runner_rank = next((i for i, p in enumerate(paths) if "runner" in p), len(paths))
        assert cli_rank is not None
        assert cli_rank < runner_rank

    def test_configmanager_query_surfaces_config_file(self, tmp_path):
        svc = _setup(tmp_path)
        results = Ranker().rank_files(svc._db, "ConfigManager", top_k=7)
        paths = [r.path for r in results]
        assert any("config_manager" in p for p in paths)
        cm_rank = next(i for i, p in enumerate(paths) if "config_manager" in p)
        assert cm_rank == 0
