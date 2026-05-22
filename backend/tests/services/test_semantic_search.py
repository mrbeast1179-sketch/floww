"""
backend/tests/services/test_semantic_search.py

Tests for the semantic search engine over trading history.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.semantic_search import (
    SemanticSearchEngine,
    TfidfEmbedder,
    cosine_similarity,
)


class TestTfidfEmbedder(unittest.TestCase):
    """Tests for the TF-IDF embedder."""

    def test_tokenize_basic(self):
        emb = TfidfEmbedder()
        tokens = emb._tokenize("Hello world test")
        self.assertEqual(tokens, ["hello", "world", "test"])

    def test_tokenize_filters_short(self):
        emb = TfidfEmbedder()
        tokens = emb._tokenize("a b c hello")
        self.assertEqual(tokens, ["hello"])

    def test_fit_builds_vocab(self):
        emb = TfidfEmbedder()
        emb.fit(["hello world", "world test", "hello test"])
        self.assertIn("hello", emb.vocab)
        self.assertIn("world", emb.vocab)
        self.assertIn("test", emb.vocab)

    def test_embed_nonzero(self):
        emb = TfidfEmbedder()
        emb.fit(["hello world", "world test"])
        vec = emb.embed("hello world")
        self.assertTrue(any(v > 0 for v in vec))

    def test_embed_normalized(self):
        emb = TfidfEmbedder()
        emb.fit(["hello world", "world test"])
        vec = emb.embed("hello world")
        norm = sum(v * v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_embed_unknown_text(self):
        emb = TfidfEmbedder()
        emb.fit(["hello world"])
        vec = emb.embed("completely unknown words")
        self.assertTrue(all(v == 0 for v in vec))

    def test_embed_batch(self):
        emb = TfidfEmbedder()
        emb.fit(["hello world", "world test", "foo bar"])
        vecs = emb.embed_batch(["hello", "world", "foo"])
        self.assertEqual(len(vecs), 3)


class TestCosineSimilarity(unittest.TestCase):
    """Tests for cosine similarity."""

    def test_identical_vectors(self):
        vec = [1.0, 0.5, 0.3]
        self.assertAlmostEqual(cosine_similarity(vec, vec), 1.0, places=5)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0, places=5)

    def test_empty_vectors(self):
        self.assertEqual(cosine_similarity([], []), 0.0)

    def test_different_lengths(self):
        self.assertEqual(cosine_similarity([1.0], [1.0, 2.0]), 0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        # Cosine sim of opposite is -1, but we clamp to 0
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0, places=5)


class TestSemanticSearchEngine(unittest.TestCase):
    """Tests for the semantic search engine."""

    def setUp(self):
        """Create a temporary database with test data."""
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_kg.duckdb")
        self._create_test_db()
        self.engine = SemanticSearchEngine(self.db_path)

    def tearDown(self):
        self.engine.close()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def _create_test_db(self):
        """Create test database with trade data."""
        conn = duckdb.connect(self.db_path)

        # Create trade tables
        conn.execute("""
            CREATE TABLE trades (
                id VARCHAR PRIMARY KEY, symbol VARCHAR, side VARCHAR,
                quantity INTEGER, entry_price DOUBLE, exit_price DOUBLE,
                pnl DOUBLE, pnl_pct DOUBLE, trade_type VARCHAR,
                entry_time VARCHAR, exit_time VARCHAR,
                holding_period_bars INTEGER, strategy VARCHAR, metadata JSON
            )
        """)
        conn.execute("""
            CREATE TABLE signals (
                id VARCHAR PRIMARY KEY, signal_type VARCHAR,
                value DOUBLE, z_score DOUBLE, threshold DOUBLE,
                direction VARCHAR, timestamp VARCHAR, metadata JSON
            )
        """)
        conn.execute("""
            CREATE TABLE market_conditions (
                id VARCHAR PRIMARY KEY, regime VARCHAR,
                volatility DOUBLE, vpin_cdf DOUBLE,
                correlation_zscore DOUBLE, timestamp VARCHAR, metadata JSON
            )
        """)
        conn.execute("""
            CREATE TABLE symbols (
                id VARCHAR PRIMARY KEY, name VARCHAR,
                asset_class VARCHAR, metadata JSON
            )
        """)
        conn.execute("""
            CREATE TABLE trade_triggered_by (
                trade_id VARCHAR, signal_id VARCHAR,
                confidence FLOAT, PRIMARY KEY (trade_id, signal_id)
            )
        """)
        conn.execute("""
            CREATE TABLE trade_executed_in (
                trade_id VARCHAR, condition_id VARCHAR,
                PRIMARY KEY (trade_id, condition_id)
            )
        """)

        # Insert test trades
        trades = [
            ("t1", "SPY", "BUY", 100, 450.0, 455.0, 500.0, 1.1, "paper",
             "2024-01-01T09:30:00", "2024-01-01T10:30:00", 10, "VPIN_HFT"),
            ("t2", "SPY", "SELL", 100, 455.0, 452.0, 300.0, 0.66, "paper",
             "2024-01-02T09:30:00", "2024-01-02T10:30:00", 8, "VPIN_HFT"),
            ("t3", "QQQ", "BUY", 50, 380.0, 375.0, -250.0, -1.32, "paper",
             "2024-01-03T09:30:00", "2024-01-03T10:30:00", 12, "VPIN_HFT"),
            ("t4", "SPY", "BUY", 200, 440.0, 448.0, 1600.0, 1.82, "paper",
             "2024-01-04T09:30:00", "2024-01-04T10:30:00", 15, "VPIN_HFT"),
            ("t5", "QQQ", "SELL", 75, 385.0, 390.0, -375.0, -1.3, "paper",
             "2024-01-05T09:30:00", "2024-01-05T10:30:00", 6, "VPIN_HFT"),
        ]
        for t in trades:
            conn.execute("""
                INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8],
                  t[9], t[10], t[11], t[12], json.dumps({})])

        # Insert test signals
        signals = [
            ("s1", "VPIN", 0.8, 2.1, 0.5, "BUY", "2024-01-01T09:30:00"),
            ("s2", "QI", -0.6, -1.8, 1.5, "SELL", "2024-01-02T09:30:00"),
            ("s3", "VPIN", 0.3, 0.8, 0.5, "BUY", "2024-01-03T09:30:00"),
            ("s4", "COMPOSITE", 1.2, 2.8, 1.0, "BUY", "2024-01-04T09:30:00"),
            ("s5", "GEX", -0.9, -2.1, 1.5, "SELL", "2024-01-05T09:30:00"),
        ]
        for s in signals:
            conn.execute("""
                INSERT INTO signals VALUES (?,?,?,?,?,?,?,?)
            """, [s[0], s[1], s[2], s[3], s[4], s[5], s[6], json.dumps({})])

        # Insert test conditions
        conditions = [
            ("c1", "low_vol", 12.5, 0.85, 3.2, "2024-01-01T09:30:00"),
            ("c2", "high_vol", 22.3, 0.72, 4.5, "2024-01-02T09:30:00"),
            ("c3", "crisis", 35.0, 0.45, 5.8, "2024-01-03T09:30:00"),
            ("c4", "trending", 14.0, 0.91, 3.5, "2024-01-04T09:30:00"),
            ("c5", "mean_reverting", 18.5, 0.65, 2.8, "2024-01-05T09:30:00"),
        ]
        for c in conditions:
            conn.execute("""
                INSERT INTO market_conditions VALUES (?,?,?,?,?,?,?)
            """, [c[0], c[1], c[2], c[3], c[4], c[5], json.dumps({})])

        # Insert edges
        edges = [
            ("t1", "s1"), ("t2", "s2"), ("t3", "s3"), ("t4", "s4"), ("t5", "s5"),
        ]
        for trade_id, signal_id in edges:
            conn.execute("""
                INSERT INTO trade_triggered_by VALUES (?, ?, 1.0)
            """, [trade_id, signal_id])

        cond_edges = [
            ("t1", "c1"), ("t2", "c2"), ("t3", "c3"), ("t4", "c4"), ("t5", "c5"),
        ]
        for trade_id, cond_id in cond_edges:
            conn.execute("""
                INSERT INTO trade_executed_in VALUES (?, ?)
            """, [trade_id, cond_id])

        conn.close()

    def test_index_trades(self):
        count = self.engine.index_trades()
        self.assertEqual(count, 5)

    def test_search_returns_results(self):
        self.engine.index_trades()
        results = self.engine.search("profitable buy trade", top_k=3)
        self.assertGreater(len(results), 0)
        self.assertIn("trade", results[0])
        self.assertIn("relevance", results[0])

    def test_search_profitable_buys(self):
        self.engine.index_trades()
        results = self.engine.search_profitable_buys(top_k=5)
        for r in results:
            self.assertEqual(r["trade"]["side"], "BUY")
            self.assertGreater(r["trade"]["pnl"], 0)

    def test_search_losing_trades(self):
        self.engine.index_trades()
        results = self.engine.search_losing_trades(top_k=5)
        for r in results:
            self.assertLess(r["trade"]["pnl"], 0)

    def test_search_by_signal(self):
        self.engine.index_trades()
        results = self.engine.search_by_signal("VPIN", top_k=5)
        self.assertGreater(len(results), 0)

    def test_search_with_filters(self):
        self.engine.index_trades()
        results = self.engine.search(
            "buy trade", top_k=10,
            filters={"symbol": "SPY", "min_pnl": 0}
        )
        for r in results:
            self.assertEqual(r["trade"]["symbol"], "SPY")
            self.assertGreater(r["trade"]["pnl"], 0)

    def test_search_results_have_signals(self):
        self.engine.index_trades()
        results = self.engine.search("VPIN buy", top_k=5)
        # At least some results should have signals
        has_signals = any(len(r.get("signals", [])) > 0 for r in results)
        self.assertTrue(has_signals)

    def test_search_results_have_conditions(self):
        self.engine.index_trades()
        results = self.engine.search("trade regime", top_k=5)
        has_conditions = any(len(r.get("conditions", [])) > 0 for r in results)
        self.assertTrue(has_conditions)

    def test_search_latency_under_1s(self):
        """Verify search completes in under 1 second."""
        import time
        self.engine.index_trades()
        start = time.monotonic()
        for _ in range(10):
            self.engine.search("profitable buy high VPIN", top_k=5)
        elapsed = time.monotonic() - start
        avg_latency = elapsed / 10
        self.assertLess(avg_latency, 1.0, f"Avg latency {avg_latency:.3f}s exceeds 1s")

    def test_trade_to_text(self):
        trade = {"side": "BUY", "symbol": "SPY", "pnl": 500.0,
                 "trade_type": "paper", "strategy": "VPIN_HFT"}
        text = self.engine._trade_to_text(trade)
        self.assertIn("BUY", text)
        self.assertIn("SPY", text)
        self.assertIn("profitable", text)

    def test_signal_to_text(self):
        signal = {"signal_type": "VPIN", "direction": "BUY", "z_score": 2.1}
        text = self.engine._signal_to_text(signal)
        self.assertIn("VPIN", text)
        self.assertIn("BUY", text)

    def test_condition_to_text(self):
        cond = {"regime": "low_vol", "volatility": 12.5, "vpin_cdf": 0.85}
        text = self.engine._condition_to_text(cond)
        self.assertIn("low_vol", text)
        self.assertIn("12.5", text)


if __name__ == "__main__":
    unittest.main()
