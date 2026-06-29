from __future__ import annotations

from pathlib import Path

import pytest

from haive.repomap.db import RepoMapDB
from haive.repomap.graph import GraphBuilder, RankedFile, Ranker
from haive.repomap.repo_map_service import RepoMapService

# --- shared fixture content (same as test_repomap_scan.py) ---

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

# --- ranking fixture with UserRegistrationHandler ---

_REGISTRATION_PY = """\
class UserRegistrationHandler:
    def handle(self, request):
        pass
"""

_REGISTRATION_CLIENT_PY = """\
from registration import UserRegistrationHandler

class RegistrationView:
    def post(self, request):
        handler = UserRegistrationHandler()
        handler.handle(request)
"""

_UNRELATED_PY = """\
def utility():
    return 42
"""


def _setup(tmp_path: Path, files: dict[str, str]) -> tuple[RepoMapService, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in files.items():
        (repo / name).write_text(content)
    db = RepoMapDB.initialize(":memory:")
    svc = RepoMapService(db, str(repo))
    svc.scan_repo(str(repo))
    return svc, repo


def _scanned(tmp_path: Path) -> RepoMapService:
    svc, _ = _setup(tmp_path, {
        "module_a.py": _MODULE_A,
        "module_b.py": _MODULE_B,
        "module_c.py": _MODULE_C,
    })
    return svc


class TestBuildEdges:
    def test_edge_created_from_importer_to_definer(self, tmp_path):
        svc = _scanned(tmp_path)
        GraphBuilder().build_edges(svc._db)
        # module_b imports ServiceA which is defined in module_a
        rows = svc._db.conn.execute("""
            SELECT f_from.path, f_to.path
            FROM edges e
            JOIN files f_from ON e.from_file_id = f_from.id
            JOIN files f_to   ON e.to_file_id   = f_to.id
        """).fetchall()
        pairs = {(r[0], r[1]) for r in rows}
        assert any("module_b" in fr and "module_a" in to for fr, to in pairs)

    def test_no_self_edges(self, tmp_path):
        svc = _scanned(tmp_path)
        GraphBuilder().build_edges(svc._db)
        count = svc._db.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE from_file_id = to_file_id"
        ).fetchone()[0]
        assert count == 0

    def test_unresolved_stdlib_imports_produce_no_edges(self, tmp_path):
        svc = _scanned(tmp_path)
        GraphBuilder().build_edges(svc._db)
        # module_a imports os and Path — neither is in our files, so no edges for those
        rows = svc._db.conn.execute("""
            SELECT symbol_name FROM edges e
            JOIN files f ON e.from_file_id = f.id
            WHERE f.path LIKE '%module_a%'
        """).fetchall()
        names = {r[0] for r in rows}
        assert "os" not in names
        assert "Path" not in names

    def test_build_edges_is_idempotent(self, tmp_path):
        svc = _scanned(tmp_path)
        gb = GraphBuilder()
        gb.build_edges(svc._db)
        count_first = svc._db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        gb.build_edges(svc._db)
        count_second = svc._db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert count_first == count_second

    def test_resolved_symbol_id_set_on_matched_references(self, tmp_path):
        svc = _scanned(tmp_path)
        GraphBuilder().build_edges(svc._db)
        resolved = svc._db.conn.execute("""
            SELECT COUNT(*) FROM "references"
            WHERE resolved_symbol_id IS NOT NULL
        """).fetchone()[0]
        assert resolved > 0


class TestRankFiles:
    def _ranked_scanned(self, tmp_path: Path) -> tuple[RepoMapService, GraphBuilder]:
        svc = _scanned(tmp_path)
        gb = GraphBuilder()
        gb.build_edges(svc._db)
        return svc, gb

    def test_query_matching_symbol_returns_defining_file_first(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        results = Ranker().rank_files(svc._db, "ServiceA", top_k=3)
        assert len(results) >= 1
        assert "module_a" in results[0].path

    def test_user_registration_handler_returns_defining_file(self, tmp_path):
        svc, _ = _setup(tmp_path, {
            "registration.py": _REGISTRATION_PY,
            "client.py": _REGISTRATION_CLIENT_PY,
            "unrelated.py": _UNRELATED_PY,
        })
        GraphBuilder().build_edges(svc._db)
        results = Ranker().rank_files(svc._db, "UserRegistrationHandler", top_k=1)
        assert len(results) == 1
        assert "registration" in results[0].path

    def test_top_k_limits_results(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        results = Ranker().rank_files(svc._db, "ServiceA", top_k=1)
        assert len(results) <= 1

    def test_unrelated_file_scores_lower_than_defining_file(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        results = Ranker().rank_files(svc._db, "ServiceA", top_k=3)
        paths = [r.path for r in results]
        if "module_c" in "".join(paths) and "module_a" in "".join(paths):
            a_idx = next(i for i, p in enumerate(paths) if "module_a" in p)
            c_idx = next(i for i, p in enumerate(paths) if "module_c" in p)
            assert a_idx < c_idx

    def test_no_match_returns_only_pagerank_results(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        # query that matches nothing — only files with incoming edges appear
        results = Ranker().rank_files(svc._db, "xyzzy_nonexistent_zzz", top_k=5)
        # module_a should rank via PageRank (imported by module_b)
        # module_c has no connections so may not appear
        for r in results:
            assert r.score > 0

    def test_reason_contains_symbol_name_for_direct_match(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        results = Ranker().rank_files(svc._db, "ServiceA", top_k=1)
        assert "ServiceA" in results[0].reason

    def test_ranked_file_has_all_fields(self, tmp_path):
        svc, _ = self._ranked_scanned(tmp_path)
        results = Ranker().rank_files(svc._db, "ServiceA", top_k=1)
        r = results[0]
        assert isinstance(r, RankedFile)
        assert r.path
        assert r.score > 0
        assert r.reason

    def test_path_match_returns_file_when_no_symbol_match(self, tmp_path):
        # query matches the file path but not any symbol name
        svc, _ = _setup(tmp_path, {
            "auth_middleware.py": "def noop(): pass\n",
            "unrelated.py": "def other(): pass\n",
        })
        GraphBuilder().build_edges(svc._db)
        results = Ranker().rank_files(svc._db, "auth", top_k=2)
        paths = [r.path for r in results]
        assert any("auth_middleware" in p for p in paths)
        auth_result = next(r for r in results if "auth_middleware" in r.path)
        assert "path matches" in auth_result.reason

    def test_ambiguous_symbol_name_produces_no_edge(self, tmp_path):
        # both files define a symbol with the same name — no edge should be created
        svc, _ = _setup(tmp_path, {
            "a.py": "def common(): pass\n",
            "b.py": "from a import common\n\ndef common(): pass\n",
        })
        GraphBuilder().build_edges(svc._db)
        count = svc._db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert count == 0

    def test_ambiguous_symbol_resolved_symbol_id_stays_null(self, tmp_path):
        svc, _ = _setup(tmp_path, {
            "a.py": "def common(): pass\n",
            "b.py": "from a import common\n\ndef common(): pass\n",
        })
        GraphBuilder().build_edges(svc._db)
        # the reference to "common" in b.py should remain unresolved
        row = svc._db.conn.execute("""
            SELECT resolved_symbol_id FROM "references"
            WHERE symbol_name = 'common'
            LIMIT 1
        """).fetchone()
        assert row is not None
        assert row[0] is None
