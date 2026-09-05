"""
backend/services/discord_ops.py

Discord operations for Tidehunter Pro: institutional-alert webhook posts
plus the command layer for the optional gateway bot (backend/discord_bot.py).

Security model (autoRSA-style, stricter):
- Alerts-out needs only DISCORD_WEBHOOK_URL ( Hels webhook, no privileged intents).
- Trading commands (!buy/!sell/!approve) execute ONLY for Discord user IDs
  in DISCORD_ALLOWED_USER_IDS. Empty allowlist = trading commands denied for
  everyone; read-only commands (!holdings/!orders/!alerts/!help) still work.
- Venue is ALWAYS Alpaca paper (paper-api.alpaca.markets is hardcoded in
  alpaca_client) — there is no live-trading code path to misconfigure.
- Secrets via env only; status endpoints report booleans, never values.

Alert gating (env, read at call time so tests can override):
- DISCORD_WEBHOOK_URL (required to post; unset = silent no-op)
- DISCORD_MIN_TIER (default GOLD)
- DISCORD_RULES (default OICONF,WHALE,SCORE,PRIME — comma list)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

_TIER_COLOR = {"GOLD": 0xE8C96A, "SILVER": 0x9AA4B2, "BRONZE": 0xCD7F32}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def webhook_url() -> str:
    return _env("DISCORD_WEBHOOK_URL", "").strip()


def min_tier() -> str:
    return _env("DISCORD_MIN_TIER", "GOLD").strip().upper() or "GOLD"


def watched_rules() -> set[str]:
    raw = _env("DISCORD_RULES", "OICONF,WHALE,SCORE,PRIME")
    return {r.strip().upper() for r in raw.split(",") if r.strip()}


def allowed_user_ids() -> set[str]:
    raw = _env("DISCORD_ALLOWED_USER_IDS", "")
    return {u.strip() for u in raw.split(",") if u.strip()}


def is_trading_allowed(user_id: str | int | None) -> bool:
    """Trading commands require a non-empty allowlist containing the user."""
    if user_id is None:
        return False
    allow = allowed_user_ids()
    return bool(allow) and str(user_id) in allow


def should_notify(alert: dict[str, Any]) -> bool:
    """Tier + rule gate for webhook posts. Pure."""
    try:
        tier = str(alert.get("tier", "BRONZE")).upper()
        rule = str(alert.get("rule", "")).upper()
    except Exception:
        return False
    if rule not in watched_rules():
        return False
    return _TIER_RANK.get(tier, 2) <= _TIER_RANK.get(min_tier(), 0)


def _fmt_money(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    a = abs(n)
    if a >= 1e9:
        return f"${n / 1e9:.2f}B"
    if a >= 1e6:
        return f"${n / 1e6:.1f}M"
    if a >= 1e3:
        return f"${n / 1e3:.0f}k"
    return f"${n:.0f}"


def format_alert_message(alert: dict[str, Any]) -> dict[str, Any]:
    """Build a Discord webhook payload (content + one rich embed). Pure."""
    tier = str(alert.get("tier", "BRONZE")).upper()
    rule = str(alert.get("rule", ""))
    under = alert.get("under", "?")
    typ = str(alert.get("type", "")).upper()
    strike = alert.get("strike", "?")
    exp = alert.get("exp", "?")
    bias = alert.get("bias") or "—"
    side = alert.get("side") or "—"
    score = alert.get("score", "—")
    premium = _fmt_money(alert.get("premium"))
    vol_oi = alert.get("vol_oi")
    vol_oi_s = f"{vol_oi:.1f}×" if isinstance(vol_oi, (int, float)) else "—"
    dte = alert.get("dte", "?")
    why = str(alert.get("why", ""))[:300]
    kl = alert.get("key_levels") or {}
    levels = ""
    if kl.get("entry") is not None:
        levels = (f"Entry {kl.get('entry')} · Invalidation {kl.get('invalidation')} "
                  f"· Target {kl.get('target')}")
    key = alert.get("key", "")
    title = f"{tier} {rule} — {under} {typ} {strike} {exp}"
    return {
        "content": f" institutional alert: **{under}** {rule} ({tier})",
        "embeds": [{
            "title": title[:256],
            "color": _TIER_COLOR.get(tier, 0x9AA4B2),
            "fields": [
                {"name": "Bias / Side", "value": f"{bias} / {side}", "inline": True},
                {"name": "Score", "value": str(score), "inline": True},
                {"name": "Premium", "value": premium, "inline": True},
                {"name": "Vol/OI", "value": vol_oi_s, "inline": True},
                {"name": "DTE", "value": str(dte), "inline": True},
                {"name": "Conviction", "value": str(alert.get("conviction", "—")), "inline": True},
                {"name": "Why", "value": why or "—", "inline": False},
                {"name": "Levels", "value": levels or "—", "inline": False},
            ],
            "footer": {"text": f"Reply !approve {key} [qty] to paper-trade this (allowlisted only)"[:2048]},
        }],
    }


async def post_alerts(alerts: list[dict[str, Any]]) -> int:
    """Post qualifying alerts to the webhook. Returns count posted. Never raises."""
    url = webhook_url()
    if not url:
        return 0
    posted = 0
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            for a in alerts or []:
                try:
                    if not should_notify(a):
                        continue
                    resp = await client.post(url, json=format_alert_message(a))
                    if resp.status_code in (200, 201, 204):
                        posted += 1
                    else:
                        logger.warning("discord webhook HTTP %s", resp.status_code)
                except Exception as e:
                    logger.warning("discord webhook post failed: %s", e)
    except Exception as e:
        logger.warning("discord webhook unavailable: %s", e)
    return posted


def parse_command(text: str) -> dict[str, Any] | None:
    """Parse `!cmd args` bot commands. Pure. Returns None when not a command."""
    if not text or not isinstance(text, str):
        return None
    parts = text.strip().split()
    if not parts or not parts[0].startswith("!"):
        return None
    cmd = parts[0][1:].lower()
    args = parts[1:]
    if cmd in ("buy", "sell") and len(args) >= 2:
        try:
            qty = int(args[0])
        except (TypeError, ValueError):
            return None
        out: dict[str, Any] = {"cmd": cmd, "qty": qty, "symbol": args[1].upper()}
        if len(args) >= 4 and args[2].lower() == "limit":
            try:
                out["limit_price"] = float(args[3])
                out["order_type"] = "limit"
            except (TypeError, ValueError):
                return None
        else:
            out["order_type"] = "market"
        return out
    if cmd == "approve" and len(args) >= 1:
        out = {"cmd": "approve", "key": args[0]}
        if len(args) >= 2:
            try:
                out["qty"] = int(args[1])
            except (TypeError, ValueError):
                return None
        return out
    if cmd in ("holdings", "positions"):
        return {"cmd": "holdings"}
    if cmd == "orders":
        return {"cmd": "orders"}
    if cmd == "alerts":
        try:
            n = int(args[0]) if args else 5
        except (TypeError, ValueError):
            return None
        return {"cmd": "alerts", "n": max(1, min(n, 10))}
    if cmd in ("help", "h"):
        return {"cmd": "help"}
    return None


HELP_TEXT = (
    "**Tidehunter paper-trading bot** (Alpaca paper ONLY)\n"
    "`!buy <qty> <SYM> [limit <px>]` · `!sell <qty> <SYM>`\n"
    "`!approve <alert-key> [qty]` — trade a posted alert\n"
    "`!holdings` · `!orders` · `!alerts [n]` · `!help`\n"
    "Trading commands require allowlist membership."
)


def fetch_recent_alerts(engine, limit: int = 10, min_tier: str = "GOLD") -> list[dict]:
    """Recent alerts for `!alerts` / `!approve` resolution. Never raises."""
    try:
        from services.flow_alerts import read_alert_feed

        return read_alert_feed(engine, days=2, min_tier=min_tier)[: max(1, int(limit))]
    except Exception as e:
        logger.warning("discord recent-alerts unavailable: %s", e)
        return []


async def execute_approve(alert_key: str, qty: int | None, engine, router) -> dict[str, Any]:
    """Execute an alert-derived paper trade. Returns a result dict (never raises).

    Direction from alert bias (BULLISH→buy, BEARISH→sell); size defaults to
    1 share; paper venue only.
    """
    try:
        rows = fetch_recent_alerts(engine, limit=50)
        alert = next((a for a in rows if a.get("key") == alert_key), None)
        if alert is None:
            return {"status": "error", "reason": f"alert not found: {alert_key}"}
        bias = str(alert.get("bias") or "").upper()
        if bias not in ("BULLISH", "BEARISH"):
            return {"status": "error", "reason": "alert has no directional bias"}
        side = "buy" if bias == "BULLISH" else "sell"
        symbol = str(alert.get("under", "")).upper()
        if not symbol:
            return {"status": "error", "reason": "alert has no underlying"}
        q = int(qty) if qty else 1
        if q <= 0:
            return {"status": "error", "reason": "qty must be positive"}
        res = await router.submit_order({
            "ticker": symbol, "side": side, "qty": q, "order_type": "market",
            "signal_id": f"discord-approve:{alert_key}",
            "timestamp_us": int(time.time() * 1e6),
        })
        return {"status": res.get("status", "error"), "order": res, "alert": alert_key}
    except Exception as e:
        logger.warning("discord approve failed: %s", e)
        return {"status": "error", "reason": str(e)}
