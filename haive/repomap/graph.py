from __future__ import annotations

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

        rows = conn.execute("""
            SELECT r.file_id, s.file_id, s.name, s.id
            FROM "references" r
            JOIN symbols s ON r.symbol_name = s.name
            WHERE r.file_id != s.file_id
            GROUP BY r.file_id, s.file_id, s.name, s.id
        """).fetchall()

        for from_file_id, to_file_id, symbol_name, symbol_id in rows:
            edge_id = conn.execute("SELECT nextval('edges_id_seq')").fetchone()[0]
            conn.execute(
                "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
                [edge_id, from_file_id, to_file_id, symbol_name, 1.0],
            )

        # resolve references to their symbol ids
        conn.execute("""
            UPDATE "references"
            SET resolved_symbol_id = s.id
            FROM symbols s
            WHERE "references".symbol_name = s.name
        """)


class Ranker:
    def rank_files(
        self, db: RepoMapDB, query: str, top_k: int
    ) -> list[RankedFile]:
        conn = db.conn
        q = query.lower()

        # --- keyword score: files that define a symbol matching the query ---
        kw_matches = conn.execute("""
            SELECT f.id, f.path, s.name
            FROM files f
            JOIN symbols s ON s.file_id = f.id
            WHERE lower(s.name) LIKE ? OR lower(s.qualified_name) LIKE ?
            ORDER BY f.id, s.start_line
        """, [f"%{q}%", f"%{q}%"]).fetchall()

        keyword_score: dict[int, float] = {}
        defining_symbol: dict[int, str] = {}
        for file_id, path, sym_name in kw_matches:
            if file_id not in keyword_score:
                keyword_score[file_id] = 1.0
                defining_symbol[file_id] = sym_name

        # --- pagerank over edges ---
        all_files = {r[0]: r[1] for r in conn.execute("SELECT id, path FROM files").fetchall()}
        edges = conn.execute("SELECT from_file_id, to_file_id FROM edges").fetchall()

        pr = _pagerank(set(all_files), edges)

        # --- combine scores ---
        in_degree: dict[int, int] = defaultdict(int)
        for _, to_id in edges:
            in_degree[to_id] += 1

        candidates: list[tuple[float, int]] = []
        for file_id in all_files:
            ks = keyword_score.get(file_id, 0.0)
            ps = pr.get(file_id, 0.0)
            combined = ks + ps
            if combined > 0:
                candidates.append((combined, file_id))

        candidates.sort(key=lambda t: -t[0])

        results: list[RankedFile] = []
        for score, file_id in candidates[:top_k]:
            path = all_files[file_id]
            if file_id in defining_symbol:
                reason = f"defines '{defining_symbol[file_id]}'"
            else:
                count = in_degree.get(file_id, 0)
                reason = f"referenced by {count} other file{'s' if count != 1 else ''}"
            results.append(RankedFile(path=path, score=score, reason=reason))

        return results


def _pagerank(
    file_ids: set[int],
    edges: list[tuple[int, int]],
) -> dict[int, float]:
    if not file_ids:
        return {}

    n = len(file_ids)
    # out-degree per node
    out_degree: dict[int, int] = defaultdict(int)
    predecessors: dict[int, list[int]] = defaultdict(list)
    for from_id, to_id in edges:
        out_degree[from_id] += 1
        predecessors[to_id].append(from_id)

    rank = {fid: 1.0 / n for fid in file_ids}

    for _ in range(_ITERATIONS):
        # dangling mass: nodes with no outgoing edges contribute to all nodes
        dangling = sum(rank[fid] for fid in file_ids if out_degree[fid] == 0)
        new_rank: dict[int, float] = {}
        for fid in file_ids:
            link_sum = sum(rank[pred] / out_degree[pred] for pred in predecessors[fid])
            new_rank[fid] = (1 - _DAMPING) / n + _DAMPING * (link_sum + dangling / n)
        rank = new_rank

    return rank
