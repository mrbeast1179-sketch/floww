"""
Synthetic data generation for ML training bootstrap.

Generates realistic synthetic GEX snapshots by:
1. Varying spot prices around current levels
2. Simulating regime changes
3. Adding realistic noise to GEX values
4. Creating price movement labels

This bootstraps the ML model until we have enough real market data.
"""

import asyncio
import numpy as np
import os
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


def generate_synthetic_snapshots(
    base_snapshot: Dict[str, Any],
    num_snapshots: int = 100,
    price_volatility: float = 0.005,  # 0.5% daily vol
    regime_change_prob: float = 0.1,  # 10% chance of regime change per step
) -> List[Dict[str, Any]]:
    """Generate synthetic snapshots from a base snapshot."""
    snapshots = []
    
    spot = base_snapshot.get("spot", 450.0)
    regime = base_snapshot.get("regime", "negative")
    total_gex = base_snapshot.get("total_gex", -1e9)
    net_gex = base_snapshot.get("net_gex", -5e8)
    king_strike = base_snapshot.get("king_strike", spot)
    king_gex = base_snapshot.get("king_gex", -1e8)
    top_floor = base_snapshot.get("top_floor", spot + 10)
    top_ceiling = base_snapshot.get("top_ceiling", spot - 10)
    strikes_compact = base_snapshot.get("strikes_compact", [])
    
    base_ts = datetime.now(timezone.utc) - timedelta(hours=num_snapshots)
    
    for i in range(num_snapshots):
        # Random walk for spot price
        price_change = np.random.normal(0, price_volatility * spot)
        spot = max(spot + price_change, 1.0)  # Keep positive
        
        # Random regime changes
        if np.random.random() < regime_change_prob:
            regime = "POSITIVE" if regime == "NEGATIVE" else "NEGATIVE"
        
        # GEX varies with price and regime
        gex_noise = np.random.normal(0, abs(total_gex) * 0.02)
        total_gex = total_gex + gex_noise
        net_gex = net_gex + gex_noise * 0.5
        
        # King strike follows price
        king_strike = spot + np.random.normal(0, 2)
        king_gex = net_gex * np.random.uniform(0.1, 0.5)
        
        # Floor/ceiling follow price
        top_floor = spot + abs(np.random.normal(10, 3))
        top_ceiling = spot - abs(np.random.normal(10, 3))
        
        # Strike distribution varies
        strikes = []
        for j in range(min(20, len(strikes_compact)) if strikes_compact else 20):
            strike_price = spot + (j - 10) * 5
            strike_gex = np.random.normal(0, abs(net_gex) / 20)
            if regime == "POSITIVE":
                strike_gex = abs(strike_gex) * (1 if strike_price > spot else -0.5)
            else:
                strike_gex = -abs(strike_gex) * (1 if strike_price < spot else -0.5)
            strikes.append({"strike": round(strike_price, 2), "gex": round(strike_gex, 0)})
        
        ts = base_ts + timedelta(minutes=5 * i)
        
        snap = {
            "ticker": base_snapshot.get("ticker", "SPY"),
            "ts": ts.isoformat(),
            "spot": round(spot, 2),
            "total_gex": round(total_gex, 0),
            "net_gex": round(net_gex, 0),
            "king_strike": round(king_strike, 2),
            "king_gex": round(king_gex, 0),
            "top_floor": round(top_floor, 2),
            "top_ceiling": round(top_ceiling, 2),
            "regime": regime,
            "strikes_compact": strikes,
        }
        
        snapshots.append(snap)
    
    logger.info(f"Generated {num_snapshots} synthetic snapshots")
    return snapshots


async def bootstrap_training_data(
    ticker: str = "SPY",
    num_snapshots: int = 200,
) -> Dict[str, Any]:
    """Bootstrap training data with synthetic snapshots."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    # Get latest real snapshot
    latest = await db.snapshots.find_one({"ticker": ticker}, sort=[("ts", -1)])
    
    if not latest:
        return {"status": "no_base_snapshot", "ticker": ticker}
    
    # Generate synthetic data
    synthetic = generate_synthetic_snapshots(latest, num_snapshots)
    
    # Insert into database
    for snap in synthetic:
        await db.snapshots.insert_one(snap)
    
    total = await db.snapshots.count_documents({"ticker": ticker})
    client.close()
    
    return {
        "status": "ok",
        "ticker": ticker,
        "synthetic_generated": num_snapshots,
        "total_snapshots": total,
    }


async def train_on_synthetic_data(
    ticker: str = "SPY",
) -> Dict[str, Any]:
    """Train ML model on synthetic + real data."""
    from ml_advanced import train_with_walkforward_cv
    
    result = await train_with_walkforward_cv(ticker, min_train_samples=30)
    return result