#!/usr/bin/env python3
"""
scripts/discover_patterns.py

Use Cypher-like queries to find common patterns in winning vs. losing trades.

Identifies actionable insights like:
  - "Winning trades often have QI Z > 2.0 and VPIN CDF > 0.7"
  - "Losing trades tend to occur in crisis regime with high volatility"
  - "COMPOSITE signals produce the highest average P&L"

Outputs: reports/patterns_<date>.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.graph_trade_service import GraphTradeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discover_patterns")

KG_DB_PATH = REPO_ROOT / "data" / "research_kg.duckdb"
REPORTS_DIR = REPO_ROOT / "reports"


class PatternDiscovery:
    """Discovers patterns in trading history using graph queries."""

    def __init__(self, db_path: str = None):
        self.service = GraphTradeService(db_path)
        self.service.ensure_schema()
        self.conn = self.service.conn

    def close(self):
        self.service.close()

    # ── Pattern 1: Signal type performance ─────────────────────────────

    def pattern_signal_performance(self) -> Dict[str, Any]:
        """Which signal types produce the best/worst P&L?"""
        rows = self.conn.execute("""
            SELECT s.signal_type,
                   COUNT(*) as trade_count,
                   AVG(t.pnl) as avg_pnl,
                   SUM(t.pnl) as total_pnl,
                   AVG(t.pnl_pct) as avg_pnl_pct,
                   SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) as losses
            FROM trades t
            JOIN trade_triggered_by ttb ON t.id = ttb.trade_id
            JOIN signals s ON ttb.signal_id = s.id
            GROUP BY s.signal_type
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            signal_type, count, avg_pnl, total_pnl, avg_pct, wins, losses = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "signal_type": signal_type,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "total_pnl": round(total_pnl or 0, 2),
                "avg_pnl_pct": round(avg_pct or 0, 4),
                "win_rate": round(win_rate, 4),
                "wins": wins,
                "losses": losses,
            })

        return {
            "name": "Signal Type Performance",
            "description": "Average P&L by signal type",
            "patterns": patterns,
            "insight": self._insight_signal_performance(patterns),
        }

    def _insight_signal_performance(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No signal data available."
        best = patterns[0]
        worst = patterns[-1] if len(patterns) > 1 else None
        insight = f"Best signal type: {best['signal_type']} (avg P&L: ${best['avg_pnl']:.2f}, win rate: {best['win_rate']:.1%})"
        if worst and worst != best:
            insight += f"\nWorst signal type: {worst['signal_type']} (avg P&L: ${worst['avg_pnl']:.2f}, win rate: {worst['win_rate']:.1%})"
        return insight

    # ── Pattern 2: Market regime analysis ──────────────────────────────

    def pattern_regime_analysis(self) -> Dict[str, Any]:
        """Which market regimes produce the best trades?"""
        rows = self.conn.execute("""
            SELECT mc.regime,
                   COUNT(*) as trade_count,
                   AVG(t.pnl) as avg_pnl,
                   SUM(t.pnl) as total_pnl,
                   AVG(mc.volatility) as avg_vol,
                   AVG(mc.vpin_cdf) as avg_vpin_cdf,
                   SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades t
            JOIN trade_executed_in tei ON t.id = tei.trade_id
            JOIN market_conditions mc ON tei.condition_id = mc.id
            GROUP BY mc.regime
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            regime, count, avg_pnl, total_pnl, avg_vol, avg_vpin, wins = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "regime": regime,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "total_pnl": round(total_pnl or 0, 2),
                "avg_volatility": round(avg_vol or 0, 2),
                "avg_vpin_cdf": round(avg_vpin or 0, 4),
                "win_rate": round(win_rate, 4),
            })

        return {
            "name": "Market Regime Analysis",
            "description": "Performance by market regime",
            "patterns": patterns,
            "insight": self._insight_regime(patterns),
        }

    def _insight_regime(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No regime data available."
        best = patterns[0]
        worst = patterns[-1] if len(patterns) > 1 else None
        insight = f"Best regime: {best['regime']} (avg P&L: ${best['avg_pnl']:.2f}, avg vol: {best['avg_volatility']:.1f})"
        if worst and worst != best:
            insight += f"\nWorst regime: {worst['regime']} (avg P&L: ${worst['avg_pnl']:.2f}, avg vol: {worst['avg_volatility']:.1f})"
        return insight

    # ── Pattern 3: Z-score thresholds ─────────────────────────────────

    def pattern_zscore_thresholds(self) -> Dict[str, Any]:
        """What z-score thresholds separate winners from losers?"""
        rows = self.conn.execute("""
            SELECT
                CASE
                    WHEN ABS(s.z_score) >= 2.5 THEN 'high (|z| >= 2.5)'
                    WHEN ABS(s.z_score) >= 1.5 THEN 'medium (1.5 <= |z| < 2.5)'
                    ELSE 'low (|z| < 1.5)'
                END as z_category,
                COUNT(*) as trade_count,
                AVG(t.pnl) as avg_pnl,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(ABS(s.z_score)) as avg_abs_z
            FROM trades t
            JOIN trade_triggered_by ttb ON t.id = ttb.trade_id
            JOIN signals s ON ttb.signal_id = s.id
            GROUP BY z_category
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            cat, count, avg_pnl, wins, avg_z = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "z_category": cat,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "win_rate": round(win_rate, 4),
                "avg_abs_z": round(avg_z or 0, 4),
            })

        return {
            "name": "Z-Score Threshold Analysis",
            "description": "Performance by signal z-score magnitude",
            "patterns": patterns,
            "insight": self._insight_zscore(patterns),
        }

    def _insight_zscore(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No z-score data available."
        best = patterns[0]
        return f"Best z-score range: {best['z_category']} (avg P&L: ${best['avg_pnl']:.2f}, win rate: {best['win_rate']:.1%})"

    # ── Pattern 4: VPIN CDF analysis ───────────────────────────────────

    def pattern_vpin_analysis(self) -> Dict[str, Any]:
        """What VPIN CDF ranges correlate with winning trades?"""
        rows = self.conn.execute("""
            SELECT
                CASE
                    WHEN mc.vpin_cdf >= 0.8 THEN 'very_high_vpin (>= 0.8)'
                    WHEN mc.vpin_cdf >= 0.6 THEN 'high_vpin (0.6-0.8)'
                    WHEN mc.vpin_cdf >= 0.4 THEN 'medium_vpin (0.4-0.6)'
                    ELSE 'low_vpin (< 0.4)'
                END as vpin_category,
                COUNT(*) as trade_count,
                AVG(t.pnl) as avg_pnl,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(mc.vpin_cdf) as avg_vpin_cdf
            FROM trades t
            JOIN trade_executed_in tei ON t.id = tei.trade_id
            JOIN market_conditions mc ON tei.condition_id = mc.id
            GROUP BY vpin_category
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            cat, count, avg_pnl, wins, avg_vpin = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "vpin_category": cat,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "win_rate": round(win_rate, 4),
                "avg_vpin_cdf": round(avg_vpin or 0, 4),
            })

        return {
            "name": "VPIN CDF Analysis",
            "description": "Performance by VPIN CDF range",
            "patterns": patterns,
            "insight": self._insight_vpin(patterns),
        }

    def _insight_vpin(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No VPIN data available."
        best = patterns[0]
        return f"Best VPIN range: {best['vpin_category']} (avg P&L: ${best['avg_pnl']:.2f}, win rate: {best['win_rate']:.1%})"

    # ── Pattern 5: Combined signal + regime ────────────────────────────

    def pattern_combined_signal_regime(self) -> Dict[str, Any]:
        """Which signal+regime combinations work best?"""
        rows = self.conn.execute("""
            SELECT s.signal_type, mc.regime,
                   COUNT(*) as trade_count,
                   AVG(t.pnl) as avg_pnl,
                   SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades t
            JOIN trade_triggered_by ttb ON t.id = ttb.trade_id
            JOIN signals s ON ttb.signal_id = s.id
            JOIN trade_executed_in tei ON t.id = tei.trade_id
            JOIN market_conditions mc ON tei.condition_id = mc.id
            GROUP BY s.signal_type, mc.regime
            HAVING trade_count >= 1
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            sig_type, regime, count, avg_pnl, wins = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "signal_type": sig_type,
                "regime": regime,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "win_rate": round(win_rate, 4),
            })

        return {
            "name": "Combined Signal + Regime",
            "description": "Performance by signal type and market regime",
            "patterns": patterns[:10],  # Top 10
            "insight": self._insight_combined(patterns[:5]),
        }

    def _insight_combined(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No combined data available."
        best = patterns[0]
        return f"Best combo: {best['signal_type']} in {best['regime']} regime (avg P&L: ${best['avg_pnl']:.2f})"

    # ── Pattern 6: Side analysis ───────────────────────────────────────

    def pattern_side_analysis(self) -> Dict[str, Any]:
        """Do BUY or SELL trades perform better?"""
        rows = self.conn.execute("""
            SELECT t.side,
                   COUNT(*) as trade_count,
                   AVG(t.pnl) as avg_pnl,
                   SUM(t.pnl) as total_pnl,
                   SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(t.holding_period_bars) as avg_holding
            FROM trades t
            GROUP BY t.side
            ORDER BY avg_pnl DESC
        """).fetchall()

        patterns = []
        for row in rows:
            side, count, avg_pnl, total_pnl, wins, avg_hold = row
            win_rate = wins / count if count > 0 else 0
            patterns.append({
                "side": side,
                "trade_count": count,
                "avg_pnl": round(avg_pnl or 0, 2),
                "total_pnl": round(total_pnl or 0, 2),
                "win_rate": round(win_rate, 4),
                "avg_holding_bars": round(avg_hold or 0, 1),
            })

        return {
            "name": "Side Analysis (BUY vs SELL)",
            "description": "Performance by trade side",
            "patterns": patterns,
            "insight": self._insight_side(patterns),
        }

    def _insight_side(self, patterns: List[Dict]) -> str:
        if not patterns:
            return "No side data available."
        parts = [f"{p['side']}: avg P&L ${p['avg_pnl']:.2f} (win rate {p['win_rate']:.1%})" for p in patterns]
        return " | ".join(parts)

    # ── Report generation ──────────────────────────────────────────────

    def discover_all(self) -> List[Dict[str, Any]]:
        """Run all pattern discovery queries."""
        results = []
        methods = [
            self.pattern_signal_performance,
            self.pattern_regime_analysis,
            self.pattern_zscore_thresholds,
            self.pattern_vpin_analysis,
            self.pattern_combined_signal_regime,
            self.pattern_side_analysis,
        ]
        for method in methods:
            try:
                result = method()
                results.append(result)
                log.info(f"Pattern '{result['name']}': {result['insight']}")
            except Exception as e:
                log.warning(f"Pattern {method.__name__} failed: {e}")
        return results

    def generate_report(self, patterns: List[Dict[str, Any]]) -> str:
        """Generate markdown report."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# Trading Pattern Discovery Report",
            f"",
            f"**Generated:** {now}",
            f"**Total Trades:** {self.service.get_trade_count()}",
            f"**Total Signals:** {self.service.get_signal_count()}",
            f"**Total Market Conditions:** {self.service.get_market_condition_count()}",
            f"",
            f"---",
            f"",
        ]

        # Trade stats
        stats = self.service.get_trade_stats()
        lines.extend([
            f"## Trade Statistics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Trades | {stats['total_trades']} |",
            f"| Profitable | {stats['profitable']} |",
            f"| Losing | {stats['losing']} |",
            f"| Win Rate | {stats['win_rate']:.1%} |",
            f"| Avg P&L | ${stats['avg_pnl']:.2f} |",
            f"| Total P&L | ${stats['total_pnl']:.2f} |",
            f"| Max P&L | ${stats['max_pnl']:.2f} |",
            f"| Min P&L | ${stats['min_pnl']:.2f} |",
            f"",
            f"---",
            f"",
        ])

        # Patterns
        for p in patterns:
            lines.extend([
                f"## {p['name']}",
                f"",
                f"*{p['description']}*",
                f"",
                f"**Insight:** {p['insight']}",
                f"",
            ])

            if p["patterns"]:
                # Table header
                headers = list(p["patterns"][0].keys())
                lines.append("| " + " | ".join(h.replace("_", " ").title() for h in headers) + " |")
                lines.append("| " + " | ".join("---" for _ in headers) + " |")
                for row in p["patterns"]:
                    lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Actionable recommendations
        lines.extend([
            f"## Actionable Recommendations",
            f"",
        ])
        for i, p in enumerate(patterns, 1):
            if p["insight"]:
                lines.append(f"{i}. **{p['name']}:** {p['insight']}")
        lines.append("")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Discover patterns in trading history")
    parser.add_argument("--db-path", type=str, default=str(KG_DB_PATH))
    parser.add_argument("--output-dir", type=str, default=str(REPORTS_DIR))
    args = parser.parse_args()

    REPORTS_DIR.mkdir(exist_ok=True)

    discovery = PatternDiscovery(args.db_path)
    try:
        patterns = discovery.discover_all()
        report = discovery.generate_report(patterns)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_path = REPORTS_DIR / f"patterns_{date_str}.md"
        output_path.write_text(report)
        log.info(f"Report written to {output_path}")
        print(report)
    finally:
        discovery.close()


if __name__ == "__main__":
    main()
