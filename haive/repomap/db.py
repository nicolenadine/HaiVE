from __future__ import annotations

import duckdb

SCHEMA_VERSION = "1"

_SEQUENCES: list[str] = [
    "CREATE SEQUENCE IF NOT EXISTS files_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS symbols_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS references_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS edges_id_seq START 1",
]

_TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        id                BIGINT PRIMARY KEY,
        path              TEXT NOT NULL UNIQUE,
        language          TEXT NOT NULL,
        content_hash      TEXT NOT NULL,
        last_indexed_at   TIMESTAMP NOT NULL,
        parser_version    TEXT NOT NULL,
        extractor_version TEXT NOT NULL,
        parse_status      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS symbols (
        id             BIGINT PRIMARY KEY,
        file_id        BIGINT NOT NULL REFERENCES files(id),
        name           TEXT NOT NULL,
        qualified_name TEXT NOT NULL,
        kind           TEXT NOT NULL,
        start_line     INTEGER NOT NULL,
        end_line       INTEGER NOT NULL,
        signature      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "references" (
        id                 BIGINT PRIMARY KEY,
        file_id            BIGINT NOT NULL REFERENCES files(id),
        symbol_name        TEXT NOT NULL,
        line_number        INTEGER NOT NULL,
        resolved_symbol_id BIGINT REFERENCES symbols(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edges (
        id           BIGINT PRIMARY KEY,
        from_file_id BIGINT NOT NULL REFERENCES files(id),
        to_file_id   BIGINT NOT NULL REFERENCES files(id),
        symbol_name  TEXT NOT NULL,
        weight       DOUBLE NOT NULL
    )
    """,
]


class SchemaMismatchError(Exception):
    pass


class RepoMapDB:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    @classmethod
    def initialize(cls, db_path: str) -> RepoMapDB:
        conn = duckdb.connect(db_path)
        db = cls(conn)
        db._apply_schema()
        return db

    def _apply_schema(self) -> None:
        # DDL runs before the version check; safe for v1 (all IF NOT EXISTS). Check version first when migrations add destructive DDL.
        for ddl in _SEQUENCES + _TABLES:
            self._conn.execute(ddl)
        stored = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if stored is None:
            self._conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)",
                [SCHEMA_VERSION],
            )
        elif stored[0] != SCHEMA_VERSION:
            raise SchemaMismatchError(
                f"Schema version mismatch: expected {SCHEMA_VERSION!r}, found {stored[0]!r}"
            )

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        return self._conn
