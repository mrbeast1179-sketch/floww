#!/usr/bin/env python3
"""
scripts/embed_trading_context.py — Embed trading-specific context into mem0.

Extracts trade signals, outcomes, market regimes, code patterns, strategy configs,
and research insights from the floww codebase and pushes them to mem0 Platform
with rich metadata for semantic search.

Usage:
    python3 scripts/embed_trading_context.py              # embed everything
    python3 scripts/embed_trading_context.py --dry-run     # show what would be embedded
    python3 scripts/embed_trading_context.py --type trade_signal  # embed specific type
    python3 scripts/embed_trading_context.py --verify      # run verification query

Verification:
    Query "best VPIN setup" should return VPIN-related configurations.
    Query "gamma flip signal" should return GAMMA_FLIP signal memories.
    Query "iron condor strategy" should return strategy config memories.
"""

import argparse
import ast
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Mem0 Client ─────────────────────────────────────────────────

def get_mem0_client():
    """Initialize mem0 Platform client from config."""
    cfg_path = Path.home() / ".mem0" / "config.json"
    if not cfg_path.exists():
        logger.error("mem0 config not found at %s", cfg_path)
        return None
    cfg = json.load(open(cfg_path))
    api_key = cfg.get("platform", {}).get("api_key")
    if not api_key:
        logger.error("No API key in mem0 config")
        return None
    try:
        from mem0 import MemoryClient
        return MemoryClient(api_key=api_key)
    except ImportError:
        logger.error("mem0ai not installed. Run: pip install mem0ai")
        return None


# ─── Extractor Functions ─────────────────────────────────────────

def extract_market_regimes():
    """Extract market regime definitions from the codebase."""
    regimes = []

    # From vpin_engine.py
    regimes.append({
        "memory": (
            "VPIN market regime thresholds: low_vol (VIX<15, VPIN_CDF<0.3), "
            "normal (VIX 15-25, VPIN_CDF<0.5), high_vol (VIX 25-35, VPIN_CDF<0.7), "
            "crisis (VIX>35, VPIN_CDF up to 1.0). "
            "Floww uses VPIN CDF z-score + Quote Imbalance z-score for regime detection. "
            "Toxicity alert fires when VPIN_CDF > 0.5 AND QI_z > 1.5."
        ),
        "metadata": {
            "type": "market_regime",
            "regime": "all",
            "source": "vpin_engine.py",
            "tags": ["market_regime", "VPIN", "floww", "config"],
        },
    })

    # From signal_translator.py
    regimes.append({
        "memory": (
            "Signal translator market regimes for trade intent generation: "
            "GEX states are positive, negative, neutral. "
            "Conviction = anomaly_score * (trinity_score/100) * (1 - vpin_cdf). "
            "Min conviction threshold is 0.7. "
            "Risk gate: account_equity > $5000, position_size <= 1% equity, "
            "max 3 open positions per ticker, Kyle's lambda < 1e-6 (illiquidity guard)."
        ),
        "metadata": {
            "type": "market_regime",
            "regime": "signal_generation",
            "source": "signal_translator.py",
            "tags": ["market_regime", "signal_translator", "floww", "risk_gates"],
        },
    })

    return regimes


def extract_trade_signals():
    """Extract trade signal definitions from the codebase."""
    signals = []

    signals.append({
        "memory": (
            "GAMMA_FLIP signal: Net Gamma Exposure (GEX) crosses zero. "
            "Formula: GEX = Σ(OI_i × Γ_i × Δ_i × 100 × Spot). "
            "When net GEX flips from positive to negative (or vice versa), "
            "dealers must reverse hedging direction — creates momentum. "
            "Urgency: HIGH. Source: Heatseeker GEX aggregator service."
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "GAMMA_FLIP",
            "ticker": "SPY",
            "urgency": "high",
            "source_service": "gex_aggregator",
            "tags": ["trade_signal", "GEX", "gamma_flip", "floww"],
        },
    })

    signals.append({
        "memory": (
            "GAMMA_SQUEEZE signal: Rapid GEX concentration at a single strike. "
            "Large open interest accumulating at one strike level, "
            "creating potential for a sharp move if price approaches. "
            "Detected by monitoring OI changes per strike vs historical baseline. "
            "Urgency: HIGH. Source: Heatseeker node classification."
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "GAMMA_SQUEEZE",
            "ticker": "SPY",
            "urgency": "high",
            "source_service": "heatseeker",
            "tags": ["trade_signal", "GEX", "gamma_squeeze", "floww"],
        },
    })

    signals.append({
        "memory": (
            "WALL_BREACH signal: Price moves through a major GEX wall. "
            "GEX walls are strikes with extreme gamma exposure that act as "
            "magnetic/resistance levels. When price breaches a wall, "
            "accelerated move often follows due to dealer re-hedging. "
            "Urgency: MEDIUM. Source: Atlas overlay + Heatseeker."
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "WALL_BREACH",
            "ticker": "SPY",
            "urgency": "medium",
            "source_service": "atlas_overlays",
            "tags": ["trade_signal", "GEX", "wall_breach", "floww"],
        },
    })

    signals.append({
        "memory": (
            "VPIN_TOXICITY signal: VPIN CDF exceeds threshold indicating informed trading. "
            "Implementation: Easley, Lopez de Prado, O'Hara (2012). "
            "Volume-clock buckets (default 50,000 units), rolling window (default 50 buckets). "
            "Bulk Volume Classification splits volume into buy/sell initiated. "
            "Alert: VPIN_CDF > 0.5. Critical: VPIN_CDF > 0.8 + QI_z > 1.5. "
            "Urgency: HIGH. Source: vpin_engine.py"
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "VPIN_TOXICITY",
            "ticker": "SPY",
            "urgency": "high",
            "source_service": "vpin_engine",
            "bucket_size": 50000,
            "window": 50,
            "tags": ["trade_signal", "VPIN", "toxicity", "floww"],
        },
    })

    signals.append({
        "memory": (
            "TRINITY_ALIGN signal: Zero-Gamma levels across SPX/SPY/QQQ align. "
            "Trinity Alignment Index = cross-correlation of zero-gamma levels, scored 0-100. "
            "Score > 60 indicates strong alignment — high-probability directional signal. "
            "When all three zero-gamma levels converge, expect a major move. "
            "Urgency: HIGH. Source: Trinity alignment service."
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "TRINITY_ALIGN",
            "ticker": "SPY",
            "urgency": "high",
            "source_service": "trinity_alignment",
            "tags": ["trade_signal", "trinity", "GEX", "floww"],
        },
    })

    signals.append({
        "memory": (
            "ANOMALY signal: 1D-CNN autoencoder detects anomalous VPIN+QI patterns. "
            "Trained on normal VPIN+QI series. Reconstruction error > 3σ = anomaly. "
            "Detects unusual flow patterns that don't match historical regimes. "
            "Can catch emerging toxicity before VPIN threshold is breached. "
            "Urgency: MEDIUM. Source: anomaly_detector.py."
        ),
        "metadata": {
            "type": "trade_signal",
            "signal_type": "ANOMALY",
            "ticker": "SPY",
            "urgency": "medium",
            "source_service": "anomaly_detector",
            "tags": ["trade_signal", "anomaly", "ML", "floww"],
        },
    })

    return signals


def extract_code_patterns():
    """Extract code patterns from the codebase with semantic annotations."""
    patterns = []

    patterns.append({
        "memory": (
            "Numba JIT Greeks calculator in numba_greeks.py: "
            "Analytical Black-Scholes Greeks (delta, gamma, vega, theta, vanna, charm) "
            "compiled to machine code via @numba.njit. "
            "Performance note: 10x faster than pure Python for batch calculations. "
            "Used by: GEX aggregator, signal translator, execution engine. "
            "File: backend/services/numba_greeks.py"
        ),
        "metadata": {
            "type": "code_pattern",
            "pattern_type": "greeks_calc",
            "language": "python",
            "file_path": "backend/services/numba_greeks.py",
            "performance_note": "Numba JIT 10x speedup",
            "tags": ["code_pattern", "Numba", "Greeks", "performance", "floww"],
        },
    })

    patterns.append({
        "memory": (
            "VPIN Engine (Easley-Lopez de Prado 2012) in vpin_engine.py: "
            "Volume-clock buckets with Bulk Volume Classification. "
            "Default: bucket_size=50000, window=50 buckets. "
            "Quote Imbalance: QI = (bid_size - ask_size) / (bid_size + ask_size). "
            "VPIN = sum(|V^B - V^S|) / sum(V) over rolling window. "
            "Empirical CDF for percentile ranking. "
            "File: backend/services/vpin_engine.py"
        ),
        "metadata": {
            "type": "code_pattern",
            "pattern_type": "execution_algo",
            "language": "python",
            "file_path": "backend/services/vpin_engine.py",
            "performance_note": "O(n) deque-based rolling window",
            "linked_signals": ["VPIN_TOXICITY", "ANOMALY"],
            "tags": ["code_pattern", "VPIN", "volume_clock", "BVC", "floww"],
        },
    })

    patterns.append({
        "memory": (
            "Almgren-Chriss optimal execution in execution_engine.py: "
            "Minimizes expected cost + risk penalty for splitting large orders. "
            "Optimal trajectory: x(t) = X * sinh(κ(T-t)) / sinh(κT). "
            "κ = sqrt(λσ²/η) where λ=risk aversion, σ=vol, η=temporary impact. "
            "Also implements Kyle's Lambda price impact and Hasbrouck's Information Share. "
            "File: backend/services/execution_engine.py"
        ),
        "metadata": {
            "type": "code_pattern",
            "pattern_type": "execution_algo",
            "language": "python",
            "file_path": "backend/services/execution_engine.py",
            "performance_note": "Closed-form optimal trajectory",
            "linked_signals": ["all"],
            "tags": ["code_pattern", "almgren_chriss", "optimal_execution", "floww"],
        },
    })

    patterns.append({
        "memory": (
            "GEX Aggregation formula in gex_aggregator.py: "
            "GEX = Σ(OI_i × Γ_i × Δ_i × 100 × Spot) for all options. "
            "Zero-Gamma Level: strike where net GEX flips sign. "
            "Positive GEX = dealers are short gamma = potential volatility suppression. "
            "Negative GEX = dealers are long gamma = potential volatility amplification. "
            "File: backend/services/gex_aggregator.py"
        ),
        "metadata": {
            "type": "code_pattern",
            "pattern_type": "greeks_calc",
            "language": "python",
            "file_path": "backend/services/gex_aggregator.py",
            "linked_signals": ["GAMMA_FLIP", "GAMMA_SQUEEZE", "WALL_BREACH", "TRINITY_ALIGN"],
            "tags": ["code_pattern", "GEX", "gamma_exposure", "aggregator", "floww"],
        },
    })

    patterns.append({
        "memory": (
            "Hawkes Process clustering in hawkes_process.py: "
            "Self-exciting point process for modeling trade clustering. "
            "Parameters: μ (baseline intensity), α (excitation), β (decay). "
            "Branching ratio α/β indicates how much each trade triggers follow-up trades. "
            "Used to detect informed trading cascades vs noise trading. "
            "Libraries: HawkesPyLib or hawkeslib. "
            "File: backend/services/hawkes_process.py"
        ),
        "metadata": {
            "type": "code_pattern",
            "pattern_type": "data_pipeline",
            "language": "python",
            "file_path": "backend/services/hawkes_process.py",
            "linked_signals": ["VPIN_TOXICITY", "ANOMALY"],
            "tags": ["code_pattern", "hawkes_process", "clustering", "floww"],
        },
    })

    return patterns


def extract_strategy_configs():
    """Extract strategy configurations from the codebase."""
    configs = []

    configs.append({
        "memory": (
            "Iron Condor strategy (floww default): "
            "Sell OTM call spread + sell OTM put spread. "
            "Max qty: 5 contracts. Max premium: $500. "
            "Allowed tickers: SPY, QQ. "
            "Risk gate: position_size <= 1% account_equity. "
            "Best in: mean_reverting regime (trinity_score < 40, VIX 15-25). "
            "Avg thesis: collect premium when market is range-bound."
        ),
        "metadata": {
            "type": "strategy_config",
            "strategy": "iron_condor",
            "parameters": {
                "max_qty": 5,
                "max_premium": 500,
                "allowed_tickers": ["SPY", "QQQ"],
            },
            "best_regime": "mean_reverting",
            "tags": ["strategy_config", "iron_condor", "floww"],
        },
    })

    configs.append({
        "memory": (
            "SPY directional strategy (paper_trading.py): "
            "Uses SPY_v1.0 model for directional signals. "
            "Risk gate: max 1% equity per trade, min account $5000. "
            "Enabled signals: GAMMA_FLIP, GAMMA_SQUEEZE, WALL_BREACH. "
            "LIVE_TRADING_ENABLED=1 required for real orders (NOT implemented). "
            "All trades go to orders_dry_run collection in Mongo. "
            "Conviction must exceed 0.7, combining anomaly, trinity, VPIN."
        ),
        "metadata": {
            "type": "strategy_config",
            "strategy": "directional_spy",
            "parameters": {
                "active_model": "SPY_v1.0",
                "enabled_signals": ["GAMMA_FLIP", "GAMMA_SQUEEZE", "WALL_BREACH"],
                "min_conviction": 0.7,
                "max_position_pct": 0.01,
            },
            "best_regime": "trending_up",
            "tags": ["strategy_config", "directional", "SPY", "floww"],
        },
    })

    return configs


def extract_research_insights():
    """Extract research insights from the codebase comments and academic refs."""
    insights = []

    insights.append({
        "memory": (
            "VPIN (Easley, Lopez de Prado, O'Hara 2012): "
            "Volume-Synchronized Probability of Informed Trading. "
            "Key finding: VPIN > 0.5 predicts short-term price reversals. "
            "VPIN CDF > 0.8 indicates extreme toxicity — informed traders active. "
            "Floww implementation: volume-clock BVC with 50k bucket, 50-bucket window. "
            "Applicability: Primary toxicity signal for all SPY trades."
        ),
        "metadata": {
            "type": "research_insight",
            "source": "arxiv",
            "title": "Flow Toxicity and Liquidity in a High-frequency World",
            "key_finding": "VPIN > 0.5 predicts reversals; CDF > 0.8 = extreme toxicity",
            "applicability": "Primary toxicity signal for SPY trades",
            "linked_code": ["backend/services/vpin_engine.py"],
            "tags": ["research_insight", "VPIN", "Easley", "Lopez_de_Prado", "floww"],
        },
    })

    insights.append({
        "memory": (
            "Almgren-Chriss optimal execution (Almgren & Chriss 2000): "
            "Minimizes E[cost] + λ * Var[cost] for splitting large orders. "
            "Optimal trajectory balances market impact vs timing risk. "
            "κ = sqrt(λσ²/η) determines urgency — higher κ = more front-loaded. "
            "Used in floww execution_engine.py for order slicing. "
            "Applicability: When trading SPY options > 5 contracts, use AC trajectory."
        ),
        "metadata": {
            "type": "research_insight",
            "source": "academic",
            "title": "Optimal Execution of Portfolio Transactions",
            "key_finding": "Closed-form optimal trajectory balancing impact vs risk",
            "applicability": "Order slicing for SPY options > 5 contracts",
            "linked_code": ["backend/services/execution_engine.py"],
            "tags": ["research_insight", "almgren_chriss", "optimal_execution", "floww"],
        },
    })

    insights.append({
        "memory": (
            "Kyle's Lambda (Kyle 1985): Price impact coefficient λ = σ_v / (2σ_u). "
            "σ_v = private info volatility, σ_u = noise trader volatility. "
            "Price impact Δp = λ × order_size. "
            "Floww uses Kyle's lambda as illiquidity guard: λ > 1e-6 blocks trade. "
            "Applicability: Prevents trading illiquid options where impact is high."
        ),
        "metadata": {
            "type": "research_insight",
            "source": "academic",
            "title": "Continuous Auctions and Insider Trading",
            "key_finding": "λ = σ_v / (2σ_u) measures price impact per unit flow",
            "applicability": "Illiquidity guard in signal_translator risk gates",
            "linked_code": ["backend/services/signal_translator.py"],
            "tags": ["research_insight", "kyle_lambda", "price_impact", "floww"],
        },
    })

    insights.append({
        "memory": (
            "Hawkes Process for trade clustering (various authors): "
            "Self-exciting point process: λ(t) = μ + Σ α·exp(-β(t-t_i)). "
            "Branching ratio α/β: expected number of child events per parent. "
            "α/β > 0.5 = strong cascade potential (informed trading cluster). "
            "Floww uses this to detect informed trading cascades in order flow. "
            "Applicability: Supplementary signal to VPIN for toxicity detection."
        ),
        "metadata": {
            "type": "research_insight",
            "source": "academic",
            "title": "Hawkes Processes in Finance",
            "key_finding": "α/β > 0.5 indicates strong cascade potential",
            "applicability": "Supplementary toxicity signal alongside VPIN",
            "linked_code": ["backend/services/hawkes_process.py"],
            "tags": ["research_insight", "hawkes_process", "clustering", "floww"],
        },
    })

    insights.append({
        "memory": (
            "GEX (Gamma Exposure) theory: "
            "Net GEX = Σ(OI × Γ × Δ × 100 × Spot) across all options. "
            "Positive GEX → dealers hedge by selling rallies / buying dips (dampening). "
            "Negative GEX → dealers hedge by buying rallies / selling dips (amplifying). "
            "Zero-Gamma Level: where net GEX = 0 — a pivot point for market structure. "
            "Trinity Alignment (SPX+SPY+QQQ zero-gamma converge) = strongest signal. "
            "Implemented in floww: gex_aggregator.py, heatseeker.py, atlas_overlays.py."
        ),
        "metadata": {
            "type": "research_insight",
            "source": "industry",
            "title": "Gamma Exposure and Market Structure",
            "key_finding": "Positive GEX dampens vol, negative GEX amplifies, zero-gamma is pivot",
            "applicability": "Foundation of all GEX-based signals in floww",
            "linked_code": [
                "backend/services/gex_aggregator.py",
                "backend/services/heatseeker.py",
                "backend/services/atlas_overlays.py",
            ],
            "tags": ["research_insight", "GEX", "gamma_exposure", "market_structure", "floww"],
        },
    })

    return insights


# ─── Trade Outcome Templates ─────────────────────────────────────

def extract_trade_outcomes():
    """Extract trade outcome templates based on paper trading logic."""
    outcomes = []

    outcomes.append({
        "memory": (
            "SPY paper trade outcome template: "
            "All trades stored in Mongo orders_dry_run collection. "
            "Entry: signal trigger + model prediction. "
            "Risk gate: max 5 contracts, max $500 premium, max 1% equity. "
            "Exit: stop_loss or take_profit from signal translator. "
            "Currently NO live submission — LIVE_TRADING_ENABLED not implemented. "
            "PnL tracking: paper PnL calculated but not persisted to mem0."
        ),
        "metadata": {
            "type": "trade_outcome",
            "ticker": "SPY",
            "strategy": "directional",
            "was_paper": True,
            "pnl_range": "unknown",
            "tags": ["trade_outcome", "paper_trading", "SPY", "floww"],
        },
    })

    return outcomes


# ─── Main Embedding Pipeline ─────────────────────────────────────

ALL_EXTRACTORS = {
    "market_regime": extract_market_regimes,
    "trade_signal": extract_trade_signals,
    "code_pattern": extract_code_patterns,
    "strategy_config": extract_strategy_configs,
    "research_insight": extract_research_insights,
    "trade_outcome": extract_trade_outcomes,
}


def embed_all(client, dry_run=False, type_filter=None):
    """Run all extractors and push to mem0."""
    total_embedded = 0
    total_skipped = 0

    for ext_name, ext_func in ALL_EXTRACTORS.items():
        if type_filter and ext_name != type_filter:
            continue

        items = ext_func()
        logger.info(f"[{ext_name}] Extracted {len(items)} items")

        for item in items:
            mem_text = item["memory"]
            metadata = item.get("metadata", {})

            if dry_run:
                logger.info(f"  [DRY] Would embed: {mem_text[:80]}...")
                total_embedded += 1
                continue

            try:
                result = client.add(
                    mem_text,
                    user_id="user_c778280e23af",
                    metadata=metadata,
                )
                if result:
                    total_embedded += 1
                    logger.info(f"  Embedded: {mem_text[:60]}...")
                else:
                    total_skipped += 1
                    logger.warning(f"  Skipped (no result): {mem_text[:60]}...")
                time.sleep(0.1)  # Rate limit
            except Exception as e:
                total_skipped += 1
                logger.error(f"  Error embedding: {e}")

    return total_embedded, total_skipped


def verify_embeddings(client):
    """Run verification queries to confirm embeddings work."""
    test_queries = [
        ("best VPIN setup", "VPIN"),
        ("gamma flip signal", "GAMMA_FLIP"),
        ("iron condor strategy", "iron_condor"),
        ("GEX aggregation formula", "GEX"),
        ("optimal execution algorithm", "Almgren-Chriss"),
        ("anomaly detection ML", "CNN autoencoder"),
        ("market regime detection", "market regime"),
        ("Kyle lambda price impact", "Kyle"),
    ]

    all_passed = True
    for query, expected_keyword in test_queries:
        try:
            result = client.search(
                query=query,
                filters={"user_id": "user_c778280e23af"},
                limit=5,
            )
            results = result.get("results", result) if isinstance(result, dict) else result
            if results:
                top = results[0]
                mem = top.get("memory", "")
                score = top.get("score", 0)
                found = expected_keyword.lower() in mem.lower()
                status = "PASS" if found else "WARN"
                if not found:
                    all_passed = False
                logger.info(f"  [{status}] '{query}' (score={score:.3f}) → {mem[:80]}...")
            else:
                all_passed = False
                logger.warning(f"  [FAIL] '{query}' → No results")
        except Exception as e:
            all_passed = False
            logger.error(f"  [ERROR] '{query}' → {e}")

    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Embed trading context into mem0")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be embedded")
    parser.add_argument("--type", dest="type_filter", help="Embed specific type only")
    parser.add_argument("--verify", action="store_true", help="Run verification queries")
    args = parser.parse_args()

    client = get_mem0_client()
    if not client:
        sys.exit(1)

    if args.verify:
        logger.info("Running verification queries...")
        passed = verify_embeddings(client)
        if passed:
            logger.info("All verification queries PASSED")
        else:
            logger.warning("Some verification queries failed — embeddings may be incomplete")
        return

    logger.info(f"Starting trading context embedding (dry_run={args.dry_run})...")
    embedded, skipped = embed_all(client, dry_run=args.dry_run, type_filter=args.type_filter)
    logger.info(f"Done. Embedded: {embedded}, Skipped: {skipped}")

    if not args.dry_run and embedded > 0:
        logger.info("\nRunning verification queries...")
        verify_embeddings(client)


if __name__ == "__main__":
    main()
