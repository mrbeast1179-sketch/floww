"""
backend/services/research/knowledge_graph.py

DuckDB-backed knowledge graph for Project Oracle research.

Schema:
  nodes:
    - paper: arxiv/ssrn/nber IDs, title, abstract, url, published_date
    - repo: GitHub owner/repo, stars, license, cloned_path
    - code_function: function_name, file_path, repo_id, category, loc
    - service: Hermes service file (e.g. gex_aggregator.py)
    - concept: extracted concept/tag (e.g. "gamma exposure", "Hawkes process")
    - author: paper/repo author

  edges:
    - paper_cites_repo: paper → repo (code link from abstract)
    - repo_implements_function: repo → code_function
    - function_belongs_to_category: code_function → concept
    - service_implements_concept: service → concept
    - paper_mentions_concept: paper → concept
    - repo_authored_by: repo → author
    - paper_authored_by: paper → author
    - function_ports_to_service: code_function → service (auto-port candidate)
    - paper_related_to_paper: paper → paper (shared concepts)

Usage:
    kg = KnowledgeGraph("/path/to/kg.duckdb")
    kg.ensure_schema()
    kg.upsert_paper({"id": "arxiv:1234", "title": "...", ...})
    kg.upsert_repo({"id": "owner/repo", "stars": 42, ...})
    kg.add_edge("paper_cites_repo", "arxiv:1234", "owner/repo")
    
    # Query
    papers = kg.find_papers_by_concept("gamma exposure")
    repos = kg.find_repos_by_category("GEX calculation")
    ports = kg.find_port_candidates()  # functions that could be ported
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("knowledge_graph")

SCHEMA_SQL = """
-- Nodes
CREATE TABLE IF NOT EXISTS papers (
    id VARCHAR PRIMARY KEY,
    title VARCHAR,
    abstract VARCHAR,
    url VARCHAR,
    source VARCHAR,
    published VARCHAR,
    discovered_at VARCHAR,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS repos (
    id VARCHAR PRIMARY KEY,
    owner VARCHAR,
    repo VARCHAR,
    stars INTEGER DEFAULT 0,
    license VARCHAR,
    cloned_path VARCHAR,
    language VARCHAR,
    loc INTEGER DEFAULT 0,
    cloned_at VARCHAR,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS code_functions (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    file_path VARCHAR,
    repo_id VARCHAR,
    category VARCHAR,
    loc INTEGER DEFAULT 0,
    has_benchmark BOOLEAN DEFAULT FALSE,
    numba_compatible BOOLEAN DEFAULT FALSE,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS services (
    id VARCHAR PRIMARY KEY,
    file_path VARCHAR,
    description VARCHAR,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS concepts (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    category VARCHAR,
    description VARCHAR,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS authors (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    affiliation VARCHAR,
    metadata JSON
);

-- Edges
CREATE TABLE IF NOT EXISTS paper_cites_repo (
    paper_id VARCHAR,
    repo_id VARCHAR,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (paper_id, repo_id)
);

CREATE TABLE IF NOT EXISTS repo_implements_function (
    repo_id VARCHAR,
    function_id VARCHAR,
    PRIMARY KEY (repo_id, function_id)
);

CREATE TABLE IF NOT EXISTS function_belongs_to_category (
    function_id VARCHAR,
    concept_id VARCHAR,
    PRIMARY KEY (function_id, concept_id)
);

CREATE TABLE IF NOT EXISTS service_implements_concept (
    service_id VARCHAR,
    concept_id VARCHAR,
    PRIMARY KEY (service_id, concept_id)
);

CREATE TABLE IF NOT EXISTS paper_mentions_concept (
    paper_id VARCHAR,
    concept_id VARCHAR,
    relevance FLOAT DEFAULT 1.0,
    PRIMARY KEY (paper_id, concept_id)
);

CREATE TABLE IF NOT EXISTS repo_authored_by (
    repo_id VARCHAR,
    author_id VARCHAR,
    PRIMARY KEY (repo_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_authored_by (
    paper_id VARCHAR,
    author_id VARCHAR,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS function_ports_to_service (
    function_id VARCHAR,
    service_id VARCHAR,
    ported BOOLEAN DEFAULT FALSE,
    port_quality FLOAT DEFAULT 0.0,
    proposal_path VARCHAR,
    PRIMARY KEY (function_id, service_id)
);

CREATE TABLE IF NOT EXISTS paper_related_to_paper (
    paper_a VARCHAR,
    paper_b VARCHAR,
    shared_concepts INTEGER DEFAULT 0,
    similarity FLOAT DEFAULT 0.0,
    PRIMARY KEY (paper_a, paper_b)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
CREATE INDEX IF NOT EXISTS idx_repos_stars ON repos(stars);
CREATE INDEX IF NOT EXISTS idx_functions_category ON code_functions(category);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);
CREATE INDEX IF NOT EXISTS idx_paper_concepts ON paper_mentions_concept(concept_id);
CREATE INDEX IF NOT EXISTS idx_repo_functions ON repo_implements_function(repo_id);
"""


class KnowledgeGraph:
    """DuckDB-backed knowledge graph for research knowledge."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(
                Path(__file__).resolve().parents[3]
                / "data"
                / "research_kg.duckdb"
            )
        self.db_path = db_path
        import duckdb
        self.conn = duckdb.connect(db_path)
        self._duckdb = duckdb

    def ensure_schema(self) -> None:
        """Create all tables and indexes if they don't exist."""
        self.conn.execute(SCHEMA_SQL)
        logger.info(f"Knowledge graph schema ensured at {self.db_path}")

    def close(self) -> None:
        self.conn.close()

    # ── Paper operations ────────────────────────────────────────────────

    def upsert_paper(self, paper: Dict[str, Any]) -> None:
        """Insert or update a paper node."""
        metadata = {k: v for k, v in paper.items()
                    if k not in ("id", "title", "abstract", "url", "source", "published", "discovered_at")}
        self.conn.execute("""
            INSERT INTO papers (id, title, abstract, url, source, published, discovered_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                abstract = excluded.abstract,
                metadata = excluded.metadata
        """, [
            paper["id"], paper.get("title"), paper.get("abstract"),
            paper.get("url"), paper.get("source"), paper.get("published"),
            paper.get("discovered_at"), json.dumps(metadata),
        ])

    def find_papers_by_concept(self, concept_name: str, limit: int = 20) -> List[Dict]:
        """Find papers that mention a given concept."""
        rows = self.conn.execute("""
            SELECT p.id, p.title, p.url, p.source, p.published, pmc.relevance
            FROM papers p
            JOIN paper_mentions_concept pmc ON p.id = pmc.paper_id
            JOIN concepts c ON pmc.concept_id = c.id
            WHERE LOWER(c.name) LIKE LOWER(?)
            ORDER BY pmc.relevance DESC, p.published DESC
            LIMIT ?
        """, [f"%{concept_name}%", limit]).fetchall()
        return [
            {"id": r[0], "title": r[1], "url": r[2], "source": r[3], "published": r[4], "relevance": r[5]}
            for r in rows
        ]

    def upsert_repo(self, repo: Dict[str, Any]) -> None:
        """Insert or update a repo node."""
        parts = repo["id"].split("/")
        owner = parts[0] if len(parts) > 0 else ""
        repo_name = parts[1] if len(parts) > 1 else ""
        metadata = {k: v for k, v in repo.items()
                    if k not in ("id", "owner", "repo", "stars", "license", "cloned_path", "language", "loc", "cloned_at")}
        self.conn.execute("""
            INSERT INTO repos (id, owner, repo, stars, license, cloned_path, language, loc, cloned_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                stars = excluded.stars,
                license = excluded.license,
                cloned_path = excluded.cloned_path
        """, [
            repo["id"], owner, repo_name, repo.get("stars", 0),
            repo.get("license"), repo.get("cloned_path"), repo.get("language"),
            repo.get("loc", 0), repo.get("cloned_at"), json.dumps(metadata),
        ])

    def find_repos_by_category(self, category: str, min_stars: int = 0, limit: int = 20) -> List[Dict]:
        """Find repos that implement functions in a given category."""
        rows = self.conn.execute("""
            SELECT DISTINCT r.id, r.owner, r.repo, r.stars, r.license, r.cloned_path
            FROM repos r
            JOIN repo_implements_function rif ON r.id = rif.repo_id
            JOIN code_functions cf ON rif.function_id = cf.id
            WHERE cf.category = ? AND r.stars >= ?
            ORDER BY r.stars DESC
            LIMIT ?
        """, [category, min_stars, limit]).fetchall()
        return [
            {"id": r[0], "owner": r[1], "repo": r[2], "stars": r[3], "license": r[4], "cloned_path": r[5]}
            for r in rows
        ]

    def upsert_function(self, func: Dict[str, Any]) -> None:
        """Insert or update a code function node."""
        metadata = {k: v for k, v in func.items()
                    if k not in ("id", "name", "file_path", "repo_id", "category", "loc", "has_benchmark", "numba_compatible")}
        self.conn.execute("""
            INSERT INTO code_functions (id, name, file_path, repo_id, category, loc, has_benchmark, numba_compatible, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                has_benchmark = excluded.has_benchmark
        """, [
            func["id"], func.get("name"), func.get("file_path"), func.get("repo_id"),
            func.get("category"), func.get("loc", 0), func.get("has_benchmark", False),
            func.get("numba_compatible", False), json.dumps(metadata),
        ])

    def add_repo_function_edge(self, repo_id: str, function_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO repo_implements_function (repo_id, function_id)
            VALUES (?, ?)
        """, [repo_id, function_id])

    def find_port_candidates(self, limit: int = 20) -> List[Dict]:
        """Find functions that are good candidates for porting to Hermes services."""
        rows = self.conn.execute("""
            SELECT cf.id, cf.name, cf.file_path, cf.repo_id, cf.category, cf.loc,
                   cf.has_benchmark, cf.numba_compatible, r.stars, r.cloned_path,
                   fpts.service_id
            FROM code_functions cf
            JOIN repo_implements_function rif ON cf.id = rif.function_id
            JOIN repos r ON rif.repo_id = r.id
            LEFT JOIN function_ports_to_service fpts ON cf.id = fpts.function_id
            WHERE cf.loc < 500
              AND (fpts.ported = FALSE OR fpts.ported IS NULL)
            ORDER BY cf.has_benchmark DESC, r.stars DESC, cf.loc ASC
            LIMIT ?
        """, [limit]).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "file_path": r[2], "repo_id": r[3],
                "category": r[4], "loc": r[5], "has_benchmark": r[6],
                "numba_compatible": r[7], "stars": r[8], "cloned_path": r[9],
                "target_service": r[10],
            }
            for r in rows
        ]

    # ── Concept operations ──────────────────────────────────────────────

    def upsert_concept(self, concept_id: str, name: str, category: str = "", description: str = "") -> None:
        self.conn.execute("""
            INSERT INTO concepts (id, name, category, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category
        """, [concept_id, name, category, description])

    def add_paper_concept_edge(self, paper_id: str, concept_id: str, relevance: float = 1.0) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO paper_mentions_concept (paper_id, concept_id, relevance)
            VALUES (?, ?, ?)
        """, [paper_id, concept_id, relevance])

    def add_function_concept_edge(self, function_id: str, concept_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO function_belongs_to_category (function_id, concept_id)
            VALUES (?, ?)
        """, [function_id, concept_id])

    def find_related_papers(self, paper_id: str, limit: int = 10) -> List[Dict]:
        """Find papers related by shared concepts."""
        rows = self.conn.execute("""
            SELECT p2.id, p2.title, p2.url, prtp.shared_concepts, prtp.similarity
            FROM paper_related_to_paper prtp
            JOIN papers p2 ON prtp.paper_b = p2.id
            WHERE prtp.paper_a = ?
            ORDER BY prtp.shared_concepts DESC, prtp.similarity DESC
            LIMIT ?
        """, [paper_id, limit]).fetchall()
        return [
            {"id": r[0], "title": r[1], "url": r[2], "shared_concepts": r[3], "similarity": r[4]}
            for r in rows
        ]

    # ── Service operations ──────────────────────────────────────────────

    def upsert_service(self, service_id: str, file_path: str, description: str = "") -> None:
        self.conn.execute("""
            INSERT INTO services (id, file_path, description)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                description = excluded.description
        """, [service_id, file_path, description])

    def add_service_concept_edge(self, service_id: str, concept_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO service_implements_concept (service_id, concept_id)
            VALUES (?, ?)
        """, [service_id, concept_id])

    # ── Edge operations ─────────────────────────────────────────────────

    def add_paper_repo_edge(self, paper_id: str, repo_id: str, confidence: float = 1.0) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO paper_cites_repo (paper_id, repo_id, confidence)
            VALUES (?, ?, ?)
        """, [paper_id, repo_id, confidence])

    def compute_paper_similarity(self) -> int:
        """Compute paper-paper similarity based on shared concepts. Returns count of pairs."""
        # Find all paper pairs that share concepts
        rows = self.conn.execute("""
            SELECT pmc1.paper_id, pmc2.paper_id, COUNT(*) as shared
            FROM paper_mentions_concept pmc1
            JOIN paper_mentions_concept pmc2
                ON pmc1.concept_id = pmc2.concept_id AND pmc1.paper_id < pmc2.paper_id
            GROUP BY pmc1.paper_id, pmc2.paper_id
            HAVING shared >= 2
        """).fetchall()

        count = 0
        for paper_a, paper_b, shared in rows:
            # Jaccard-like similarity
            total_a = self.conn.execute(
                "SELECT COUNT(*) FROM paper_mentions_concept WHERE paper_id = ?", [paper_a]
            ).fetchone()[0]
            total_b = self.conn.execute(
                "SELECT COUNT(*) FROM paper_mentions_concept WHERE paper_id = ?", [paper_b]
            ).fetchone()[0]
            union = total_a + total_b - shared
            similarity = shared / union if union > 0 else 0

            self.conn.execute("""
                INSERT OR REPLACE INTO paper_related_to_paper (paper_a, paper_b, shared_concepts, similarity)
                VALUES (?, ?, ?, ?)
            """, [paper_a, paper_b, shared, similarity])
            count += 1

        logger.info(f"Computed {count} paper-paper relationships")
        return count

    def get_stats(self) -> Dict[str, int]:
        """Return node/edge counts."""
        return {
            "papers": self.get_paper_count(),
            "repos": self.get_repo_count(),
            "functions": self.conn.execute("SELECT COUNT(*) FROM code_functions").fetchone()[0],
            "services": self.conn.execute("SELECT COUNT(*) FROM services").fetchone()[0],
            "concepts": self.conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0],
            "paper_repo_edges": self.conn.execute("SELECT COUNT(*) FROM paper_cites_repo").fetchone()[0],
            "repo_function_edges": self.conn.execute("SELECT COUNT(*) FROM repo_implements_function").fetchone()[0],
            "port_candidates": len(self.find_port_candidates(limit=1000)),
        }

    def get_concept_summary(self, limit: int = 20) -> List[Dict]:
        """Get top concepts by paper count."""
        rows = self.conn.execute("""
            SELECT c.id, c.name, c.category, COUNT(pmc.paper_id) as paper_count
            FROM concepts c
            LEFT JOIN paper_mentions_concept pmc ON c.id = pmc.concept_id
            GROUP BY c.id, c.name, c.category
            ORDER BY paper_count DESC
            LIMIT ?
        """, [limit]).fetchall()
        return [{"id": r[0], "name": r[1], "category": r[2], "paper_count": r[3]} for r in rows]
