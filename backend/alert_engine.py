"""
Options Alert System for Confluence Decoder

Combines signals from:
- GEX regime changes (gamma flip, positive/negative)
- Wall breaches (call wall, put wall)
- Gamma squeeze detection
- Momentum extremes
- GEX magnitude shifts (dealer repositioning)
- Pin risk (max gamma strike proximity)
- Volume spikes at near-ATM strikes

Based on research from:
- neeleshroy2023/gex-alerts: signal detection engine
- FlashAlpha: GEX/DEX/VEX/CHEX exposure levels
- Matteo-Ferrara/gex-tracker: GEX calculation
- Proshotv2/Gamma-Vanna: vanna exposure
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """A single trading alert."""
    type: str           # GAMMA_FLIP, WALL_BREACH, GAMMA_SQUEEZE, etc.
    priority: str       # HIGH, MEDIUM, LOW
    ticker: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "priority": self.priority,
            "ticker": self.ticker,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class GEXSnapshot:
    """Snapshot of GEX data at a point in time."""
    ticker: str
    spot_price: float
    gamma_flip: float
    call_wall: float
    put_wall: float
    max_pain: float
    max_gamma_strike: float
    total_gex: float
    net_gex: float
    regime: str  # "POSITIVE" or "NEGATIVE"
    gex_by_strike: Dict[float, float] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class AlertEngine:
    """
    Detects trading alerts by comparing GEX snapshots over time.
    Based on the signal detection algorithm from neeleshroy2023/gex-alerts.
    """
    
    # Configurable thresholds
    GAMMA_SQUEEZE_PROXIMITY_PCT = 0.5   # Spot within 0.5% of flip
    WALL_BREACH_PROXIMITY_PCT = 0.1     # 0.1% beyond wall = breach
    GEX_MAGNITUDE_SHIFT_PCT = 40.0      # 40% GEX change = significant
    GAMMA_FLIP_PROXIMITY_PCT = 0.3      # Within 0.3% of flip = inflection
    PIN_RISK_PROXIMITY_PCT = 0.2        # Within 0.2% of max gamma strike
    VOLUME_SPIKE_MULTIPLIER = 2.0       # 2x volume = spike
    MOMENTUM_EXTREME_HIGH = 80          # Score > 80 = extreme bullish
    MOMENTUM_EXTREME_LOW = 20           # Score < 20 = extreme bearish
    
    def __init__(self):
        self._snapshots: Dict[str, List[GEXSnapshot]] = {}
    
    def add_snapshot(self, snapshot: GEXSnapshot):
        """Store a new snapshot for comparison."""
        ticker = snapshot.ticker
        if ticker not in self._snapshots:
            self._snapshots[ticker] = []
        self._snapshots[ticker].append(snapshot)
        
        # Keep only last 100 snapshots per ticker
        if len(self._snapshots[ticker]) > 100:
            self._snapshots[ticker] = self._snapshots[ticker][-100:]
    
    def get_latest(self, ticker: str) -> Optional[GEXSnapshot]:
        """Get the latest snapshot for a ticker."""
        snapshots = self._snapshots.get(ticker, [])
        return snapshots[-1] if snapshots else None
    
    def get_previous(self, ticker: str) -> Optional[GEXSnapshot]:
        """Get the second-to-last snapshot for comparison."""
        snapshots = self._snapshots.get(ticker, [])
        return snapshots[-2] if len(snapshots) >= 2 else None
    
    def detect_alerts(self, ticker: str, momentum_score: int = 50) -> List[Alert]:
        """
        Compare current vs previous snapshot and detect trading alerts.
        Returns alerts sorted by priority (HIGH first).
        """
        current = self.get_latest(ticker)
        previous = self.get_previous(ticker)
        
        if not current:
            return []
        
        alerts: List[Alert] = []
        spot = current.spot_price
        
        # 1. GAMMA FLIP (HIGH) — regime changed sign
        if previous and previous.regime != current.regime:
            direction = "SHORT gamma — expect amplified moves" if current.regime == "NEGATIVE" else "LONG gamma — expect mean reversion"
            alerts.append(Alert(
                type="GAMMA_FLIP",
                priority="HIGH",
                ticker=ticker,
                message=f"⚠️ REGIME CHANGE: {previous.regime} → {current.regime}. Dealers now {direction}",
                data={
                    "old_regime": previous.regime,
                    "new_regime": current.regime,
                    "gamma_flip": current.gamma_flip,
                    "net_gex": current.net_gex,
                }
            ))
        
        # 2. GAMMA SQUEEZE (HIGH) — negative gamma + spot near flip + volume spike
        if current.regime == "NEGATIVE" and previous:
            flip_dist_pct = abs(spot - current.gamma_flip) / spot * 100 if spot > 0 else 999
            if flip_dist_pct < self.GAMMA_SQUEEZE_PROXIMITY_PCT:
                volume_spike = self._detect_volume_spike(current, previous)
                if volume_spike:
                    alerts.append(Alert(
                        type="GAMMA_SQUEEZE",
                        priority="HIGH",
                        ticker=ticker,
                        message=f"🔥 GAMMA SQUEEZE forming — negative regime, spot {spot:.0f} within {flip_dist_pct:.1f}% of flip at {current.gamma_flip:.0f}, volume spiking",
                        data={
                            "flip_distance_pct": round(flip_dist_pct, 2),
                            "gamma_flip": current.gamma_flip,
                            "regime": current.regime,
                        }
                    ))
        
        # 3. MOMENTUM EXTREME (HIGH)
        if momentum_score > self.MOMENTUM_EXTREME_HIGH:
            alerts.append(Alert(
                type="MOMENTUM_EXTREME",
                priority="HIGH",
                ticker=ticker,
                message=f"📈 Strong BULLISH momentum — score {momentum_score}/100",
                data={"momentum_score": momentum_score, "direction": "BULLISH"}
            ))
        elif momentum_score < self.MOMENTUM_EXTREME_LOW:
            alerts.append(Alert(
                type="MOMENTUM_EXTREME",
                priority="HIGH",
                ticker=ticker,
                message=f"📉 Strong BEARISH momentum — score {momentum_score}/100",
                data={"momentum_score": momentum_score, "direction": "BEARISH"}
            ))
        
        # 4. WALL BREACH (MEDIUM)
        if current.call_wall > 0:
            breach_pct = (spot - current.call_wall) / current.call_wall * 100
            if breach_pct > self.WALL_BREACH_PROXIMITY_PCT:
                alerts.append(Alert(
                    type="WALL_BREACH",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🚀 BULLISH breakout — spot {spot:.0f} breached call wall at {current.call_wall:.0f} (+{breach_pct:.2f}%)",
                    data={"wall": current.call_wall, "direction": "BULLISH", "breach_pct": round(breach_pct, 2)}
                ))
        
        if current.put_wall > 0:
            breach_pct = (current.put_wall - spot) / current.put_wall * 100
            if breach_pct > self.WALL_BREACH_PROXIMITY_PCT:
                alerts.append(Alert(
                    type="WALL_BREACH",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🔻 BEARISH breakdown — spot {spot:.0f} breached put wall at {current.put_wall:.0f} (-{breach_pct:.2f}%)",
                    data={"wall": current.put_wall, "direction": "BEARISH", "breach_pct": round(breach_pct, 2)}
                ))
        
        # 5. GEX MAGNITUDE SHIFT (MEDIUM) — total GEX changed > 40%
        if previous and previous.total_gex != 0:
            gex_change_pct = abs(current.total_gex - previous.total_gex) / abs(previous.total_gex) * 100
            if gex_change_pct > self.GEX_MAGNITUDE_SHIFT_PCT:
                alerts.append(Alert(
                    type="GEX_MAGNITUDE_SHIFT",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"⚡ GEX shifted {gex_change_pct:.0f}% — rapid dealer repositioning detected",
                    data={
                        "change_pct": round(gex_change_pct, 1),
                        "old_gex": previous.total_gex,
                        "new_gex": current.total_gex,
                    }
                ))
        
        # 6. GAMMA FLIP PROXIMITY (MEDIUM) — spot within 0.3% of flip
        flip_proximity = abs(spot - current.gamma_flip) / spot * 100 if spot > 0 else 999
        if flip_proximity < self.GAMMA_FLIP_PROXIMITY_PCT:
            if not any(a.type == "GAMMA_FLIP" for a in alerts):
                alerts.append(Alert(
                    type="GAMMA_FLIP_PROXIMITY",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🔄 Spot {spot:.0f} within {flip_proximity:.2f}% of gamma flip at {current.gamma_flip:.0f} — inflection zone",
                    data={"gamma_flip": current.gamma_flip, "distance_pct": round(flip_proximity, 2)}
                ))
        
        # 7. PIN RISK (LOW) — spot near max gamma strike
        pin_proximity = abs(spot - current.max_gamma_strike) / spot * 100 if spot > 0 else 999
        if pin_proximity < self.PIN_RISK_PROXIMITY_PCT:
            alerts.append(Alert(
                type="PIN_RISK",
                priority="LOW",
                ticker=ticker,
                message=f"📌 Pin risk — spot {spot:.0f} within {pin_proximity:.2f}% of max gamma strike {current.max_gamma_strike:.0f}",
                data={"max_gamma_strike": current.max_gamma_strike, "distance_pct": round(pin_proximity, 2)}
            ))
        
        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        alerts.sort(key=lambda a: priority_order.get(a.priority, 9))
        
        return alerts
    
    def _detect_volume_spike(self, current: GEXSnapshot, previous: GEXSnapshot) -> bool:
        """Check if any near-ATM strike has a volume spike vs previous cycle."""
        if not previous.gex_by_strike or not current.gex_by_strike:
            return False
        
        spot = current.spot_price
        near_strikes = [
            s for s in current.gex_by_strike
            if abs(s - spot) / spot < 0.02  # within 2% of spot
        ]
        
        for strike in near_strikes:
            cur_gex = abs(current.gex_by_strike.get(strike, 0))
            prev_gex = abs(previous.gex_by_strike.get(strike, 0))
            if prev_gex > 0 and cur_gex / prev_gex > self.VOLUME_SPIKE_MULTIPLIER:
                return True
        
        return False
    
    def get_alert_summary(self, ticker: str) -> Dict[str, Any]:
        """Get a summary of current alerts for a ticker."""
        latest = self.get_latest(ticker)
        if not latest:
            return {"ticker": ticker, "status": "no_data"}
        
        alerts = self.detect_alerts(ticker)
        
        return {
            "ticker": ticker,
            "spot": latest.spot_price,
            "regime": latest.regime,
            "gamma_flip": latest.gamma_flip,
            "call_wall": latest.call_wall,
            "put_wall": latest.put_wall,
            "net_gex": latest.net_gex,
            "alert_count": len(alerts),
            "high_priority": len([a for a in alerts if a.priority == "HIGH"]),
            "alerts": [a.to_dict() for a in alerts],
            "timestamp": datetime.utcnow().isoformat(),
        }
