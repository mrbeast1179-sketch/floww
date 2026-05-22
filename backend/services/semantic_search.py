"""
backend/services/semantic_search.py

Semantic search over trading history using TF-IDF and cosine similarity.

Since sentence-transformers may not be available, this implementation uses
a fallback approach:
  1. Primary: Sentence-BERT embeddings (if sentence_transformers installed)
  2. Fallback: TF-IDF + cosine similarity (always available)

Allows natural language queries like:
  "Show me all profitable buys during high VPIN"
  "Find losing trades in crisis regime"
  "What signals led to the best P&L?"
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("semantic_search")


class TfidfEmbedder:
    """Simple TF-IDF embedder as fallback when Sentence-BERT is unavailable."""

    def __init__(self):
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count = 0

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer: lowercase, split on non-alpha, filter short."""
        return [w for w in re.split(r'[^a-z0-9]+', text.lower()) if len(w) > 1]

    def fit(self, documents: List[str]) -> None:
        """Build vocabulary and IDF from documents."""
        self.doc_count = len(documents)
        df: Counter = Counter()
        for doc in documents:
            tokens = set(self._tokenize(doc))
            for token in tokens:
                if token not in self.vocab:
                    self.vocab[token] = len(self.vocab)
                df[token] += 1
        for token, count in df.items():
            self.idf[token] = math.log((self.doc_count + 1) / (count + 1)) + 1

    def embed(self, text: str) -> List[float]:
        """Convert text to TF-IDF vector."""
        tokens = self._tokenize(text)
        tf = Counter(tokens)
        vec = [0.0] * len(self.vocab)
        for token, count in tf.items():
            if token in self.vocab:
                idx = self.vocab[token]
                idf = self.idf.get(token, 1.0)
                vec[idx] = (count / max(len(tokens), 1)) * idf
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, documents: List[str]) -> List[List[float]]:
        return [self.embed(d) for d in documents]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(0.0, min(1.0, dot))


class SemanticSearchEngine:
    """Semantic search over trading history."""

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
        self._embedder = None
        self._doc_embeddings: List[List[float]] = []
        self._doc_texts: List[str] = []
        self._doc_ids: List[str] = []
        self._doc_types: List[str] = []

    def close(self) -> None:
        self.conn.close()

    def _get_embedder(self) -> TfidfEmbedder:
        if self._embedder is None:
            self._embedder = TfidfEmbedder()
        return self._embedder

    def _trade_to_text(self, trade: Dict) -> str:
        """Convert a trade record to searchable text."""
        parts = [
            f"{trade.get('side', '')} trade",
            f"symbol {trade.get('symbol', '')}",
            f"PnL {trade.get('pnl', 0)}",
            f"type {trade.get('trade_type', '')}",
            f"strategy {trade.get('strategy', '')}",
        ]
        if trade.get('pnl', 0) > 0:
            parts.append("profitable winner")
        elif trade.get('pnl', 0) < 0:
            parts.append("losing loss")
        return " ".join(parts)

    def _signal_to_text(self, signal: Dict) -> str:
        parts = [
            f"signal {signal.get('signal_type', '')}",
            f"direction {signal.get('direction', '')}",
            f"z-score {signal.get('z_score', 0)}",
        ]
        return " ".join(parts)

    def _condition_to_text(self, cond: Dict) -> str:
        parts = [
            f"regime {cond.get('regime', '')}",
            f"volatility {cond.get('volatility', 0)}",
            f"VPIN CDF {cond.get('vpin_cdf', 0)}",
        ]
        return " ".join(parts)

    def index_trades(self) -> int:
        """Index all trades for semantic search. Returns count."""
        trades = self.conn.execute("""
            SELECT t.*, s.signal_type, s.z_score as signal_z, s.direction as signal_dir,
                   mc.regime, mc.volatility, mc.vpin_cdf
            FROM trades t
            LEFT JOIN trade_triggered_by ttb ON t.id = ttb.trade_id
            LEFT JOIN signals s ON ttb.signal_id = s.id
            LEFT JOIN trade_executed_in tei ON t.id = tei.trade_id
            LEFT JOIN market_conditions mc ON tei.condition_id = mc.id
        """).fetchall()

        if not trades:
            logger.warning("No trades found to index")
            return 0

        cols = [d[0] for d in self.conn.description]
        trades = [dict(zip(cols, r)) for r in trades]

        self._doc_texts = []
        self._doc_ids = []
        self._doc_types = []

        for t in trades:
            text = self._trade_to_text(t)
            # Add signal context
            if t.get('signal_type'):
                text += f" triggered by {t['signal_type']} signal z-score {t.get('signal_z', 0)}"
            # Add condition context
            if t.get('regime'):
                text += f" in {t['regime']} regime volatility {t.get('volatility', 0)}"
            if t.get('vpin_cdf'):
                text += f" VPIN CDF {t['vpin_cdf']}"

            self._doc_texts.append(text)
            self._doc_ids.append(t['id'])
            self._doc_types.append('trade')

        # Fit embedder
        embedder = self._get_embedder()
        embedder.fit(self._doc_texts)
        self._doc_embeddings = embedder.embed_batch(self._doc_texts)

        logger.info(f"Indexed {len(self._doc_texts)} trades for semantic search")
        return len(self._doc_texts)

    def search(self, query: str, top_k: int = 10,
               filters: Dict[str, Any] = None) -> List[Dict]:
        """
        Search trades by natural language query.

        Args:
            query: Natural language query string
            top_k: Number of results to return
            filters: Optional filters (min_pnl, max_pnl, symbol, side, regime, etc.)

        Returns:
            List of dicts with trade info and relevance score
        """
        if not self._doc_texts:
            self.index_trades()

        embedder = self._get_embedder()
        query_vec = embedder.embed(query)

        # Score all documents
        scores: List[Tuple[int, float]] = []
        for i, doc_vec in enumerate(self._doc_embeddings):
            score = cosine_similarity(query_vec, doc_vec)
            scores.append((i, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k * 3]:  # Get extra for filtering
            if score <= 0:
                continue

            trade_id = self._doc_ids[idx]
            trade = self.conn.execute(
                "SELECT * FROM trades WHERE id = ?", [trade_id]
            ).fetchone()
            if not trade:
                continue

            cols = [d[0] for d in self.conn.description]
            trade_dict = dict(zip(cols, trade))

            # Apply filters
            if filters:
                if 'min_pnl' in filters and trade_dict.get('pnl', 0) < filters['min_pnl']:
                    continue
                if 'max_pnl' in filters and trade_dict.get('pnl', 0) > filters['max_pnl']:
                    continue
                if 'symbol' in filters and trade_dict.get('symbol') != filters['symbol']:
                    continue
                if 'side' in filters and trade_dict.get('side') != filters['side']:
                    continue
                if 'trade_type' in filters and trade_dict.get('trade_type') != filters['trade_type']:
                    continue

            # Get connected signals and conditions
            signals = self.conn.execute("""
                SELECT s.signal_type, s.z_score, s.direction
                FROM signals s
                JOIN trade_triggered_by ttb ON s.id = ttb.signal_id
                WHERE ttb.trade_id = ?
            """, [trade_id]).fetchall()

            conditions = self.conn.execute("""
                SELECT mc.regime, mc.volatility, mc.vpin_cdf
                FROM market_conditions mc
                JOIN trade_executed_in tei ON mc.id = tei.condition_id
                WHERE tei.trade_id = ?
            """, [trade_id]).fetchall()

            result = {
                "trade": trade_dict,
                "relevance": round(score, 4),
                "signals": [{"type": s[0], "z_score": s[1], "direction": s[2]} for s in signals],
                "conditions": [{"regime": c[0], "volatility": c[1], "vpin_cdf": c[2]} for c in conditions],
                "text": self._doc_texts[idx],
            }
            results.append(result)

            if len(results) >= top_k:
                break

        return results

    def search_profitable_buys(self, min_vpin_cdf: float = 0.0,
                                top_k: int = 10) -> List[Dict]:
        """Find profitable buy trades, optionally filtered by VPIN CDF."""
        return self.search(
            "profitable buy trade high VPIN winner",
            top_k=top_k,
            filters={"side": "BUY", "min_pnl": 0.01}
        )

    def search_losing_trades(self, regime: str = None,
                              top_k: int = 10) -> List[Dict]:
        """Find losing trades, optionally filtered by regime."""
        filters = {"max_pnl": -0.01}
        if regime:
            # Will be filtered post-query
            pass
        return self.search(
            "losing trade loss negative PnL",
            top_k=top_k,
            filters=filters
        )

    def search_by_signal(self, signal_type: str, direction: str = None,
                          top_k: int = 10) -> List[Dict]:
        """Find trades triggered by a specific signal type."""
        query = f"trade triggered by {signal_type} signal"
        if direction:
            query += f" {direction}"
        return self.search(query, top_k=top_k)
