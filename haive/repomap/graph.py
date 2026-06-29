from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

from haive.repomap.db import RepoMapDB

_DAMPING = 0.85
_ITERATIONS = 20


@dataclass
class RankedFile:
    path: str
    score: float
    reason: str


class GraphBuilder:
    def build_edges(self, db: RepoMapDB) -> None:
        conn = db.conn
        conn.execute("DELETE FROM edges")

        # Only create edges for unambiguous matches: symbol name maps to exactly
        # one symbol row globally. Common names like run/save/__init__ that appear
        # in multiple files are skipped to avoid noisy cross-file edges.
        rows = conn.execute("""
            WITH unambiguous AS (
                SELECT name, MIN(id) AS symbol_id, MIN(file_id) AS to_file_id
                FROM symbols
                GROUP BY name
                HAVING COUNT(*) = 1
            )
            SELECT DISTINCT r.file_id AS from_file_id, u.to_file_id, u.name
            FROM "references" r
            JOIN unambiguous u ON r.symbol_name = u.name
            WHERE r.file_id != u.to_file_id
        """).fetchall()

        for from_file_id, to_file_id, symbol_name in rows:
            edge_id = conn.execute("SELECT nextval('edges_id_seq')").fetchone()[0]
            conn.execute(
                "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
                [edge_id, from_file_id, to_file_id, symbol_name, 1.0],
            )

        # Set resolved_symbol_id only when the name is unambiguous (one symbol globally).
        conn.execute("""
            WITH unique_matches AS (
                SELECT name, MIN(id) AS symbol_id, COUNT(*) AS match_count
                FROM symbols
                GROUP BY name
            )
            UPDATE "references"
            SET resolved_symbol_id = unique_matches.symbol_id
            FROM unique_matches
            WHERE "references".symbol_name = unique_matches.name
              AND unique_matches.match_count = 1
        """)


class Ranker:
    def rank_files(
        self, db: RepoMapDB, query: str, top_k: int
    ) -> list[RankedFile]:
        conn = db.conn
        tokens = _tokenize_query(query)
        all_files = {r[0]: r[1] for r in conn.execute("SELECT id, path FROM files").fetchall()}
        edges = conn.execute("SELECT from_file_id, to_file_id FROM edges").fetchall()

        # Fetch all symbols once; match each token against them separately
        all_symbols = conn.execute(
            "SELECT file_id, name, qualified_name FROM symbols"
        ).fetchall()

        # For each token: which files have a matching symbol or path?
        token_file_matches: dict[str, set[int]] = {}
        token_sym_matches: dict[str, list[tuple[int, str]]] = {}
        for token in tokens:
            file_matches: set[int] = set()
            sym_hits: list[tuple[int, str]] = []
            for sym_fid, name, qname in all_symbols:
                if token in name.lower() or token in qname.lower():
                    file_matches.add(sym_fid)
                    sym_hits.append((sym_fid, name))
            for fid, path in all_files.items():
                if token in path.lower():
                    file_matches.add(fid)
            if file_matches:
                token_file_matches[token] = file_matches
                token_sym_matches[token] = sym_hits

        # IDF-weighted seed: files matching rare/specific tokens score higher
        raw_seed: dict[int, float] = {}
        for token, file_ids in token_file_matches.items():
            w = _idf_weight(len(file_ids))
            for fid in file_ids:
                raw_seed[fid] = raw_seed.get(fid, 0.0) + w

        # Track the best matching symbol per file using the most specific token first
        defining_symbol: dict[int, str] = {}
        tokens_by_specificity = sorted(
            token_file_matches, key=lambda t: _idf_weight(len(token_file_matches[t])), reverse=True
        )
        for token in tokens_by_specificity:
            for sym_fid, sym_name in token_sym_matches.get(token, []):
                if sym_fid not in defining_symbol:
                    defining_symbol[sym_fid] = sym_name

        # Personalized PageRank seeded from keyword-matched files.
        # Falls back to uniform distribution when no tokens match.
        total = sum(raw_seed.values())
        seed = {fid: v / total for fid, v in raw_seed.items()} if total > 0 else None
        pr = _pagerank(set(all_files), edges, seed=seed)

        in_degree: dict[int, int] = defaultdict(int)
        for _, to_id in edges:
            in_degree[to_id] += 1

        candidates: list[tuple[float, int]] = []
        for file_id in all_files:
            ks = raw_seed.get(file_id, 0.0)
            ppr = pr.get(file_id, 0.0)
            combined = ks + ppr
            if combined > 0:
                candidates.append((combined, file_id))

        candidates.sort(key=lambda t: -t[0])

        results: list[RankedFile] = []
        for score, file_id in candidates[:top_k]:
            path = all_files[file_id]
            if file_id in defining_symbol:
                reason = f"defines '{defining_symbol[file_id]}'"
            elif file_id in raw_seed:
                reason = "path matches query"
            else:
                count = in_degree.get(file_id, 0)
                reason = f"referenced by {count} other file{'s' if count != 1 else ''}"
            results.append(RankedFile(path=path, score=score, reason=reason))

        return results


def _tokenize_query(query: str) -> list[str]:
    tokens = re.split(r"[^\w]+", query.lower())
    return [t for t in tokens if len(t) >= 3]


def _idf_weight(df: int) -> float:
    return 1.0 / (1.0 + math.log(1.0 + df))


def _pagerank(
    file_ids: set[int],
    edges: list[tuple[int, int]],
    seed: dict[int, float] | None = None,
) -> dict[int, float]:
    if not file_ids:
        return {}

    n = len(file_ids)
    out_degree: dict[int, int] = defaultdict(int)
    predecessors: dict[int, list[int]] = defaultdict(list)
    for from_id, to_id in edges:
        out_degree[from_id] += 1
        predecessors[to_id].append(from_id)

    if seed is None:
        seed = {fid: 1.0 / n for fid in file_ids}

    rank = {fid: seed.get(fid, 0.0) for fid in file_ids}

    for _ in range(_ITERATIONS):
        dangling = sum(rank[fid] for fid in file_ids if out_degree[fid] == 0)
        new_rank: dict[int, float] = {}
        for fid in file_ids:
            link_sum = sum(rank[pred] / out_degree[pred] for pred in predecessors[fid])
            new_rank[fid] = (1 - _DAMPING) * seed.get(fid, 0.0) + _DAMPING * (link_sum + dangling / n)
        rank = new_rank

    return rank
