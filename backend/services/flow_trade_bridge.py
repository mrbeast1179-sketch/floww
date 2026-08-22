"""
backend/services/flow_trade_bridge.py

Signal-to-trade bridge: converts qualifying institutional flow alerts
(from services.flow_alerts, persisted in flow_alerts_daily) into
(1) paper-trading orders compatible with PaperTradingEngine.submit_order,
(2) journal seed entries matching the frontend's floww_trades_v2 schema.

Eligibility gates (all must pass):
  tier in {SILVER, GOLD}          — conviction floor (configurable)
  side == "BUY"                   — directional claims only; FLOW/STRATEGY
                                    never auto-trade (desk rule: never claim
                                    a side you can't defend)
  dte >= min_dte (default 2)      — architect mandate: skip same-day 0DTE;
                                    take the forward-dated contracts
  est_entry is a positive number  — BS-priced entry required for sizing

Position sizing: fixed-fraction risk — notional = RISK_PCT * equity, so
quantity = floor(risk_notional / (est_entry * 100)), minimum 1 contract.

Pure logic only; the route layer handles persistence and engine calls.
"""

from __future__ import annotations

import math
from typing import Any

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

RISK_PCT_PER_TRADE = 0.02   # 2% of account equity per position
DEFAULT_MIN_DTE = 2         # skip same-day + next-day expiries


def eligible_for_auto_trade(alert: dict, *, min_tier: str = "SILVER",
                            min_dte: int = DEFAULT_MIN_DTE) -> bool:
    """All gates must pass for an alert to become an auto paper-trade."""
    if not isinstance(alert, dict):
        return False
    tier = str(alert.get("tier") or "").upper()
    min_rank = _TIER_RANK.get(min_tier.upper(), _TIER_RANK["SILVER"])
    if _TIER_RANK.get(tier, 99) > min_rank:
        return False
    if str(alert.get("side") or "").upper() != "BUY":
        return False
    dte = alert.get("dte")
    if not isinstance(dte, (int, float)) or isinstance(dte, bool) or dte < min_dte:
        return False
    entry = alert.get("est_entry")
    if not isinstance(entry, (int, float)) or isinstance(entry, bool):
        return False
    return entry > 0


def _position_size(est_entry: float, account_equity: float,
                   conviction: int | None = None) -> int:
    """Fixed-fraction base (2% of equity) scaled by Blademap-style
    conviction: ≥75 conviction takes full size, 60–75 takes 75%, below
    60 takes half. Min 1 contract. Conviction is the ranked 0-100
    score from flow_alerts.score_conviction (None → full size)."""
    scale = 1.0
    if isinstance(conviction, (int, float)) and not isinstance(conviction, bool):
        if conviction >= 75:
            scale = 1.0
        elif conviction >= 60:
            scale = 0.75
        else:
            scale = 0.5
    risk_notional = max(account_equity, 0.0) * RISK_PCT_PER_TRADE * scale
    per_contract = max(est_entry, 0.01) * 100.0
    qty = int(math.floor(risk_notional / per_contract)) if per_contract > 0 else 0
    return max(qty, 1)


def alert_to_order(alert: dict, *, account_equity: float = 100_000.0) -> dict[str, Any]:
    """Alert → PaperTradingEngine.submit_order kwargs."""
    entry = float(alert["est_entry"])
    return {
        "symbol": str(alert["under"]).upper(),
        "side": "BUY",
        "quantity": _position_size(entry, account_equity,
                                   conviction=alert.get("conviction")),
        "order_type": "market",
        "metadata": {
            "source": "flowseeker",
            "ckey": alert.get("ckey"),
            "alert_key": alert.get("key"),
            "rule": alert.get("rule"),
            "tier": alert.get("tier"),
            "contract_type": alert.get("type"),
            "strike": alert.get("strike"),
            "expiry": alert.get("exp"),
            "dte": alert.get("dte"),
            "est_entry": entry,
            "under_price": alert.get("under_price"),
        },
    }


def alert_to_journal_entry(alert: dict) -> dict[str, Any]:
    """Alert → floww_trades_v2-shaped seed entry (TradeJournal localStorage
    schema): ticker, type, action, strike, expiry, quantity, entry_price,
    exit_price, entry_date, exit_date, notes, gex_regime, setup, tags."""
    under = str(alert.get("under") or "").upper()
    setup = f"{str(alert.get('rule') or 'flow').lower()} {str(alert.get('tier') or '').lower()}"
    why = str(alert.get("why") or "")
    notes = (
        f"Auto-seeded from Flowseeker Pro ({setup}). "
        f"vol/OI {alert.get('vol_oi')}x, ~${(alert.get('premium') or 0) / 1e6:.1f}M premium, "
        f"{alert.get('dte')} DTE. {why}"
    )
    return {
        "ticker": under,
        "type": str(alert.get("type") or "call").lower(),
        "action": "buy",
        "strike": alert.get("strike"),
        "expiry": alert.get("exp"),
        "quantity": "1",           # journal tracks contracts; sizing lives in paper engine
        "entry_price": alert.get("est_entry"),
        "exit_price": "",
        "entry_date": str(alert.get("asof") or "")[:10],
        "exit_date": "",
        "notes": notes,
        "gex_regime": "",
        "setup": setup,
        "tags": "flowseeker,auto",
    }


def dedupe_alerts(alerts: list[dict]) -> list[dict]:
    """One trade per contract key — first occurrence wins (alerts arrive
    tier-ranked, strongest-first)."""
    seen: set[str] = set()
    out: list[dict] = []
    for a in alerts:
        ckey = a.get("ckey")
        if not ckey or ckey in seen:
            continue
        seen.add(ckey)
        out.append(a)
    return out


def build_auto_trades(alerts: list[dict], *, account_equity: float = 100_000.0,
                      min_tier: str = "SILVER",
                      min_dte: int = DEFAULT_MIN_DTE) -> list[dict]:
    """Full pipeline: filter → dedupe → shape. Returns dicts with both the
    order payload and the journal seed so one call feeds both consumers."""
    out: list[dict] = []
    for a in dedupe_alerts(list(alerts or [])):
        if not eligible_for_auto_trade(a, min_tier=min_tier, min_dte=min_dte):
            continue
        out.append({
            "order": alert_to_order(a, account_equity=account_equity),
            "journal_entry": alert_to_journal_entry(a),
            "ckey": a.get("ckey"),
            "tier": a.get("tier"),
            "under": a.get("under"),
        })
    return out
