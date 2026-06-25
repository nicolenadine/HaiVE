from __future__ import annotations

from pathlib import Path

import pytest

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


def _setup(tmp_path: Path) -> tuple[RepoMapService, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module_a.py").write_text(_MODULE_A)
    (repo / "module_b.py").write_text(_MODULE_B)
    db = RepoMapDB.initialize(":memory:")
    svc = RepoMapService(db, str(repo))
    svc.scan_repo(str(repo))
    return svc, repo


class TestUpdateFilesSkip:
    def test_unchanged_file_is_skipped(self, tmp_path):
        svc, repo = _setup(tmp_path)
        sym_count_before = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        ts_before = svc._db.conn.execute(
            "SELECT last_indexed_at FROM files WHERE path = 'module_a.py'"
        ).fetchone()[0]
        svc.update_files(["module_a.py"])
        sym_count_after = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        ts_after = svc._db.conn.execute(
            "SELECT last_indexed_at FROM files WHERE path = 'module_a.py'"
        ).fetchone()[0]
        assert sym_count_before == sym_count_after
        assert ts_before == ts_after

    def test_unknown_extension_is_skipped(self, tmp_path):
        svc, repo = _setup(tmp_path)
        (repo / "README.md").write_text("# docs\n")
        file_count_before = svc._db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        svc.update_files(["README.md"])
        file_count_after = svc._db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert file_count_before == file_count_after

    def test_nonexistent_path_is_skipped(self, tmp_path):
        svc, repo = _setup(tmp_path)
        sym_count_before = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        svc.update_files(["ghost.py"])  # must not raise
        sym_count_after = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        assert sym_count_before == sym_count_after


class TestUpdateFilesReparse:
    def test_changed_file_is_reparsed(self, tmp_path):
        svc, repo = _setup(tmp_path)
        (repo / "module_a.py").write_text("def new_function(): pass\n")
        svc.update_files(["module_a.py"])
        names = {r[0] for r in svc._db.conn.execute("SELECT name FROM symbols").fetchall()}
        assert "new_function" in names
        assert "helper" not in names
        assert "ServiceA" not in names

    def test_unrelated_file_unchanged_after_update(self, tmp_path):
        svc, repo = _setup(tmp_path)
        sym_b_before = svc._db.conn.execute(
            "SELECT COUNT(*) FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = 'module_b.py'"
        ).fetchone()[0]
        (repo / "module_a.py").write_text("def new_function(): pass\n")
        svc.update_files(["module_a.py"])
        sym_b_after = svc._db.conn.execute(
            "SELECT COUNT(*) FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = 'module_b.py'"
        ).fetchone()[0]
        assert sym_b_before == sym_b_after


class TestUpdateFilesEdges:
    def test_edges_rebuilt_after_update(self, tmp_path):
        svc, repo = _setup(tmp_path)
        GraphBuilder().build_edges(svc._db)
        edges_before = svc._db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert edges_before > 0
        # remove the import so module_b no longer references module_a
        (repo / "module_b.py").write_text("class ClientB:\n    def execute(self):\n        pass\n")
        svc.update_files(["module_b.py"])
        rows = svc._db.conn.execute("""
            SELECT f_from.path, f_to.path
            FROM edges e
            JOIN files f_from ON e.from_file_id = f_from.id
            JOIN files f_to   ON e.to_file_id   = f_to.id
        """).fetchall()
        assert not any("module_b" in fr and "module_a" in to for fr, to in rows)

    def test_broken_reference_after_symbol_removed(self, tmp_path):
        svc, repo = _setup(tmp_path)
        GraphBuilder().build_edges(svc._db)
        # verify ServiceA is resolved before the change
        resolved_before = svc._db.conn.execute(
            'SELECT resolved_symbol_id FROM "references" WHERE symbol_name = \'ServiceA\' LIMIT 1'
        ).fetchone()
        assert resolved_before is not None and resolved_before[0] is not None
        # remove ServiceA from module_a
        (repo / "module_a.py").write_text("def helper(x): return x * 2\n")
        svc.update_files(["module_a.py"])
        # module_b still references ServiceA, but it's no longer defined anywhere
        row = svc._db.conn.execute(
            'SELECT resolved_symbol_id FROM "references" WHERE symbol_name = \'ServiceA\' LIMIT 1'
        ).fetchone()
        assert row is not None
        assert row[0] is None
