from __future__ import annotations

from datetime import datetime, timezone

import pytest

from haive.repomap.db import SCHEMA_VERSION, RepoMapDB, SchemaMismatchError

_EXPECTED_TABLES = {"schema_meta", "files", "symbols", "references", "edges"}


def _table_names(db: RepoMapDB) -> set[str]:
    return {row[0] for row in db.conn.execute("SHOW TABLES").fetchall()}


def test_initialize_creates_all_tables() -> None:
    db = RepoMapDB.initialize(":memory:")
    assert _EXPECTED_TABLES <= _table_names(db)


def test_files_columns() -> None:
    db = RepoMapDB.initialize(":memory:")
    cols = {row[0] for row in db.conn.execute("DESCRIBE files").fetchall()}
    assert cols == {"id", "path", "language", "content_hash", "last_indexed_at",
                    "parser_version", "extractor_version", "parse_status"}


def test_symbols_columns() -> None:
    db = RepoMapDB.initialize(":memory:")
    cols = {row[0] for row in db.conn.execute("DESCRIBE symbols").fetchall()}
    assert cols == {"id", "file_id", "name", "qualified_name", "kind",
                    "start_line", "end_line", "signature"}


def test_references_columns() -> None:
    db = RepoMapDB.initialize(":memory:")
    cols = {row[0] for row in db.conn.execute('DESCRIBE "references"').fetchall()}
    assert cols == {"id", "file_id", "symbol_name", "line_number", "resolved_symbol_id"}


def test_edges_columns() -> None:
    db = RepoMapDB.initialize(":memory:")
    cols = {row[0] for row in db.conn.execute("DESCRIBE edges").fetchall()}
    assert cols == {"id", "from_file_id", "to_file_id", "symbol_name", "weight"}


def test_schema_version_stored_on_fresh_init() -> None:
    db = RepoMapDB.initialize(":memory:")
    row = db.conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


def test_apply_schema_twice_does_not_error_or_drop_data() -> None:
    db = RepoMapDB.initialize(":memory:")
    db.conn.execute(
        "INSERT INTO files VALUES (1, 'a.py', 'python', 'abc123', ?, '1', '1', 'ok')",
        [datetime.now(timezone.utc)],
    )
    db._apply_schema()
    count = db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 1
    assert _EXPECTED_TABLES <= _table_names(db)


def test_schema_version_mismatch_raises() -> None:
    db = RepoMapDB.initialize(":memory:")
    db.conn.execute(
        "UPDATE schema_meta SET value = '999' WHERE key = 'schema_version'"
    )
    with pytest.raises(SchemaMismatchError, match="999"):
        db._apply_schema()
