from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from haive.models.context import BrokenReference, ContextPack, RelevantFile, RelevantSymbol
from haive.models.task import Task
from haive.repomap.db import RepoMapDB
from haive.repomap.graph import Ranker
from haive.repomap.language_parser import LanguageParser, ParsedFile, PythonParser

_PRUNE_DIRS = {"__pycache__", ".git"}


class RepoMapService:
    def __init__(self, db: RepoMapDB, root: str = "") -> None:
        self._db = db
        self._root = root

    def scan_repo(
        self,
        root: str,
        parsers: list[LanguageParser] | None = None,
    ) -> None:
        if parsers is None:
            parsers = [PythonParser()]

        ext_map: dict[str, LanguageParser] = {
            ext: parser for parser in parsers for ext in parser.extensions
        }
        gitignore = _load_gitignore(root)

        if not _any_matching_files(root, ext_map, gitignore):
            warnings.warn(
                f"No files matching registered parsers ({list(ext_map)}) found in {root!r}",
                stacklevel=2,
            )

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
            for filename in filenames:
                ext = os.path.splitext(filename)[1]
                parser = ext_map.get(ext)
                if parser is None:
                    continue
                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, root)
                if _is_ignored(rel_path, gitignore):
                    continue
                content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
                parsed = parser.parse_file(rel_path, content)
                self._upsert_file(rel_path, parser.language, parsed)

    def _upsert_file(self, path: str, language: str, parsed: ParsedFile) -> None:
        existing = self._db.conn.execute(
            "SELECT id, content_hash FROM files WHERE path = ?", [path]
        ).fetchone()

        if existing is not None:
            if existing[1] == parsed.content_hash:
                return  # unchanged — skip
            # changed file: remove stale symbols and references
            file_id = existing[0]
            self._db.conn.execute(
                'DELETE FROM "references" WHERE file_id = ?', [file_id]
            )
            self._db.conn.execute(
                "DELETE FROM symbols WHERE file_id = ?", [file_id]
            )
            self._db.conn.execute(
                "UPDATE files SET content_hash = ?, last_indexed_at = ?, "
                "parser_version = ?, extractor_version = ?, parse_status = 'ok' "
                "WHERE id = ?",
                [parsed.content_hash, _now(), parsed.parser_version,
                 parsed.extractor_version, file_id],
            )
        else:
            file_id = self._db.conn.execute(
                "SELECT nextval('files_id_seq')"
            ).fetchone()[0]
            self._db.conn.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [file_id, path, language, parsed.content_hash, _now(),
                 parsed.parser_version, parsed.extractor_version, "ok"],
            )

        for sym in parsed.symbols:
            sym_id = self._db.conn.execute(
                "SELECT nextval('symbols_id_seq')"
            ).fetchone()[0]
            self._db.conn.execute(
                "INSERT INTO symbols VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [sym_id, file_id, sym.name, sym.qualified_name,
                 sym.kind, sym.start_line, sym.end_line, sym.signature],
            )

        for ref in parsed.references:
            ref_id = self._db.conn.execute(
                "SELECT nextval('references_id_seq')"
            ).fetchone()[0]
            self._db.conn.execute(
                'INSERT INTO "references" VALUES (?, ?, ?, ?, ?)',
                [ref_id, file_id, ref.symbol_name, ref.line_number, None],
            )

    def get_context_pack(self, task: Task, token_budget: int) -> ContextPack:
        conn = self._db.conn
        query = f"{task.title} {task.description}"
        ranked = Ranker().rank_files(self._db, query, top_k=10)

        ranked_ids = []
        for rf in ranked:
            row = conn.execute("SELECT id FROM files WHERE path = ?", [rf.path]).fetchone()
            if row:
                ranked_ids.append(row[0])

        # relevant_files preserves ranked order
        relevant_files = [RelevantFile(path=rf.path, reason=rf.reason) for rf in ranked]

        # symbols in ranked order, by start_line within each file
        relevant_symbols: list[RelevantSymbol] = []
        for file_id, rf in zip(ranked_ids, ranked):
            abs_path = Path(self._root) / rf.path
            try:
                lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            syms = conn.execute(
                "SELECT qualified_name, kind, start_line, end_line FROM symbols "
                "WHERE file_id = ? ORDER BY start_line",
                [file_id],
            ).fetchall()
            for qname, kind, start, end in syms:
                source = "\n".join(lines[start - 1 : end])
                relevant_symbols.append(RelevantSymbol(
                    qualified_name=qname,
                    kind=kind,
                    file_path=rf.path,
                    start_line=start,
                    end_line=end,
                    source=source,
                ))

        # broken references from ranked files only
        broken_references: list[BrokenReference] = []
        if ranked_ids:
            placeholders = ", ".join("?" * len(ranked_ids))
            rows = conn.execute(
                f'SELECT f.path, r.symbol_name, r.line_number '
                f'FROM "references" r JOIN files f ON r.file_id = f.id '
                f'WHERE r.resolved_symbol_id IS NULL AND r.file_id IN ({placeholders})',
                ranked_ids,
            ).fetchall()
            broken_references = [
                BrokenReference(file_path=p, symbol_name=s, line_number=ln)
                for p, s, ln in rows
            ]

        # impacted files: have an edge TO a ranked file, not themselves ranked
        impacted_files: list[str] = []
        if ranked_ids:
            placeholders = ", ".join("?" * len(ranked_ids))
            rows = conn.execute(
                f"SELECT DISTINCT f.path FROM files f "
                f"JOIN edges e ON e.from_file_id = f.id "
                f"WHERE e.to_file_id IN ({placeholders}) "
                f"AND f.id NOT IN ({placeholders})",
                ranked_ids + ranked_ids,
            ).fetchall()
            impacted_files = [r[0] for r in rows]

        # trim from the bottom until within token_budget
        token_estimate = sum(len(s.source) for s in relevant_symbols) // 4
        while token_estimate > token_budget and relevant_symbols:
            relevant_symbols.pop()
            token_estimate = sum(len(s.source) for s in relevant_symbols) // 4

        return ContextPack(
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            impacted_files=impacted_files,
            broken_references=broken_references,
            token_estimate=token_estimate,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_gitignore(root: str) -> list[str]:
    # Simple fnmatch patterns only — no negation, anchored paths, or nested .gitignore. Use pathspec for real Git semantics.
    path = os.path.join(root, ".gitignore")
    if not os.path.exists(path):
        return []
    patterns = []
    with open(path) as f:
        for line in f:
            line = line.strip().rstrip("/")
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def _is_ignored(rel_path: str, patterns: list[str]) -> bool:
    name = os.path.basename(rel_path)
    return any(fnmatch(rel_path, p) or fnmatch(name, p) for p in patterns)


def _any_matching_files(
    root: str, ext_map: dict[str, LanguageParser], gitignore: list[str]
) -> bool:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for f in filenames:
            if os.path.splitext(f)[1] in ext_map:
                rel = os.path.relpath(os.path.join(dirpath, f), root)
                if not _is_ignored(rel, gitignore):
                    return True
    return False
