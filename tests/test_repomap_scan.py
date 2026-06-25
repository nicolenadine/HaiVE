from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from haive.repomap.db import RepoMapDB
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


def _make_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module_a.py").write_text(_MODULE_A)
    (repo / "module_b.py").write_text(_MODULE_B)
    (repo / "module_c.py").write_text(_MODULE_C)
    return repo


def _service(tmp_path: Path) -> tuple[RepoMapService, Path]:
    repo = _make_fixture(tmp_path)
    db = RepoMapDB.initialize(":memory:")
    return RepoMapService(db, str(repo)), repo


class TestScanRepoPopulates:
    def test_files_table_has_one_row_per_py_file(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        count = svc._db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 3

    def test_symbols_table_has_rows(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        count = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        assert count > 0

    def test_references_table_has_rows(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        count = svc._db.conn.execute('SELECT COUNT(*) FROM "references"').fetchone()[0]
        assert count > 0

    def test_import_reference_recorded(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        row = svc._db.conn.execute(
            'SELECT 1 FROM "references" WHERE symbol_name = ?', ["ServiceA"]
        ).fetchone()
        assert row is not None

    def test_class_symbol_recorded(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        row = svc._db.conn.execute(
            "SELECT kind FROM symbols WHERE name = ?", ["ServiceA"]
        ).fetchone()
        assert row is not None
        assert row[0] == "class"

    def test_method_symbol_recorded_with_qualified_name(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        row = svc._db.conn.execute(
            "SELECT qualified_name FROM symbols WHERE name = ? AND kind = 'method'",
            ["run"],
        ).fetchone()
        assert row is not None
        assert row[0] == "ServiceA.run"


class TestScanRepoIdempotency:
    def test_scan_twice_does_not_duplicate_rows(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        count_after_first = svc._db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        svc.scan_repo(str(repo))
        count_after_second = svc._db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count_after_first == count_after_second

    def test_scan_twice_does_not_duplicate_symbols(self, tmp_path):
        svc, repo = _service(tmp_path)
        svc.scan_repo(str(repo))
        sym_count = svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        svc.scan_repo(str(repo))
        assert svc._db.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == sym_count


class TestScanRepoNonPyFiles:
    def test_non_py_file_is_skipped(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def f(): pass\n")
        (repo / "README.md").write_text("# Readme\n")
        (repo / "config.yaml").write_text("key: value\n")
        db = RepoMapDB.initialize(":memory:")
        svc = RepoMapService(db, str(repo))
        svc.scan_repo(str(repo))
        paths = {r[0] for r in db.conn.execute("SELECT path FROM files").fetchall()}
        assert all(p.endswith(".py") for p in paths)
        assert len(paths) == 1

    def test_no_py_files_emits_warning(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# hi\n")
        db = RepoMapDB.initialize(":memory:")
        svc = RepoMapService(db, str(repo))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            svc.scan_repo(str(repo))
        assert any(".py" in str(w.message) or "parsers" in str(w.message) for w in caught)

    def test_pycache_dirs_are_skipped(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("def f(): pass\n")
        pycache = repo / "__pycache__"
        pycache.mkdir()
        (pycache / "main.cpython-311.pyc").write_bytes(b"\x00" * 16)
        db = RepoMapDB.initialize(":memory:")
        svc = RepoMapService(db, str(repo))
        svc.scan_repo(str(repo))
        paths = {r[0] for r in db.conn.execute("SELECT path FROM files").fetchall()}
        assert not any("__pycache__" in p for p in paths)
