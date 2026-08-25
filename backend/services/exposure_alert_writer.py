"""Map exposure_alerts events onto the flow_alerts_daily row shape.

O-2 of GSD #10: scheduler evaluates exposure alerts post-insert and writes
them into the existing flow-alerts DuckDB table via flow_alerts.persist_alerts
so they surface in the conviction feed unchanged.
"""

from __future__ import annotations

from datetime import datetime

from services.exposure_alerts import evaluate_exposure_events

_TIER_BY_KIND = {
    "vex_wall_formed": "GOLD",
    "vex_wall_broken": "GOLD",
    "charm_pin_shifted": "SILVER",
    "charm_pin_formed": "BRONZE",
}

_WHYS = {
    "vex_wall_formed": "VEX wall formed — dealer vanna suppression level",
    "vex_wall_broken": "VEX wall broken — vol-suppression level lost",
    "charm_pin_formed": "Charm pin formed — delta-hedge concentration",
    "charm_pin_shifted": "Charm pin shifted — hedge magnet moved",
}


def events_to_alerts(ticker: str, spot: float, events: list[dict],
                     now: datetime | None = None) -> list[dict]:
    """Convert evaluator events to persist_alerts-compatible dicts."""
    ts = (now or datetime.now()).isoformat()
    out = []
    for e in events:
        kind = e.get("kind", "")
        strike = float(e.get("strike") or 0)
        mag = float(e.get("magnitude") or 0)
        out.append({
            "asof": ts,
            # Dedup key: one row per ticker/kind/strike/expiry/day (persist_alerts
            # upserts on (asof_date, key), so repeats overwrite not duplicate).
            "key": f"exposure:{kind}:{ticker}:{e.get('expiry', '')}:{strike:g}",
            "rule": f"exposure_{kind}",
            "tier": _TIER_BY_KIND.get(kind, "BRONZE"),
            "side": None,
            "bias": "bullish" if mag >= 0 else "bearish",
            "under": ticker.upper(),
            "type": "exposure",
            "strike": strike,
            "exp": e.get("expiry"),
            "score": min(99, max(50, int(abs(mag) / 1e6) + 50)),
            "under_price": spot,
            "why": _WHYS.get(kind, kind),
            "context": {"magnitude": mag},
        })
    return out


def evaluate_and_convert(new_grid: dict, old_grid: dict | None,
                         ticker: str, spot: float,
                         threshold_pct: float = 0.25) -> list[dict]:
    """One-call helper for _snapshot_chains: evaluate then map."""
    return events_to_alerts(
        ticker, spot, evaluate_exposure_events(new_grid, old_grid, threshold_pct))
