#!/usr/bin/env python3
"""
Nightly outcome-refresh for the Tidehunter Pro alert ledger.

Precomputes the outcome-measurement stats (services/flow_outcomes.py) and
caches them in Mongo (flow_outcome_cache), so:
  • the morning brief / Scanner outcome panel read a precomputed table
    instead of recomputing the bars-join on every request, and
  • the calibration stage gate (flow_calibration.py) has a stable, dated
    snapshot of n per rule to decide stage promotion.

Run via cron AFTER the market close and after yfinance daily bars settle:
    30 20 * * 1-5  (20:30 ET ≈ 00:30 UTC next day; see crontab line)

Usage: .venv/bin/python3 cron_outcomes.py [--days 60] [--horizon 2] [--push]
  --push  also POST the result to the running backend's cache-warm endpoint
          (default: just write Mongo directly — no server needed)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cron_outcomes")


async def refresh(days: int, horizon: int, push: bool) -> dict:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    from motor.motor_asyncio import AsyncIOMotorClient

    from services import flow_outcomes as fo
    from services.duckdb_engine import db as duckdb_engine

    # 1. Alert ledger (read-only DuckDB)
    alerts = fo.read_alert_history(duckdb_engine, days=days)
    if not alerts:
        log.info("no alerts in ledger within %dd — nothing to refresh", days)
        return {"status": "no_alerts", "days": days}

    tickers = sorted({a.get("under") for a in alerts if a.get("under")})
    log.info("labeling %d alerts across %d tickers (horizon=%d)", len(alerts), len(tickers), horizon)

    # 2. Bars + VIX (free; network calls off the event loop)
    loop = asyncio.get_running_loop()
    bars = await loop.run_in_executor(None, fo.fetch_bars_yfinance, tickers)
    vix = await loop.run_in_executor(None, fo.fetch_bars_yfinance, ["^VIX"])
    if not bars:
        log.warning("yfinance bars unavailable — skipping this refresh (last good cache stays)")
        return {"status": "no_bars", "days": days}

    # 3. Compute + cache
    stats = fo.compute_outcomes(alerts, bars, vix.get("^VIX"), horizon=horizon)
    stats["ok"] = True
    stats["lookback_days"] = days
    stats["computed_at"] = datetime.now(UTC).isoformat()
    stats["status"] = "ok"

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "floww")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        db = client[db_name]
        await db.flow_outcome_cache.update_one(
            {"_id": f"outcomes_h{horizon}"},
            {"$set": stats},
            upsert=True,
        )
        log.info("cached outcomes to %s.flow_outcome_cache (_id=outcomes_h%d): %s",
                 db_name, horizon, json.dumps(stats.get("overall", {}), default=str)[:160])
        # Calibration snapshot — same labeling pass feeds the stage ladder
        # (stage 0 below n=60; the cron is what lets stage 1+ ever promote).
        try:
            from services import flow_calibration as fc
            labeled = fo.label_alerts(alerts, bars, vix.get("^VIX"), horizon=horizon)
            cal = fc.fit_calibration(labeled)
            cal_doc = {"_id": "calibration_latest", "ok": True,
                       "computed_at": stats["computed_at"], **cal}
            cal_doc.pop("model", None) if cal_doc.get("model") is None else None
            await db.flow_outcome_cache.update_one(
                {"_id": "calibration_latest"}, {"$set": cal_doc}, upsert=True)
            log.info("cached calibration: stage=%s n=%s (%s)",
                     cal.get("stage"), cal.get("n"), cal.get("method_note", "")[:60])
        except Exception as e:
            log.warning("calibration fit skipped: %s", e)
    finally:
        client.close()

    # 4. Optional: warm a RUNNING backend's in-process view too. POSTs are
    # fail-closed behind X-API-Key (auth middleware) — the cron reads the same
    # .env, so it sends the header itself.
    if push:
        import httpx
        try:
            headers = {}
            api_key = os.environ.get("API_SECRET_KEY", "")
            if api_key:
                headers["X-API-Key"] = api_key
            async with httpx.AsyncClient(timeout=10) as hc:
                resp = await hc.post("http://localhost:8000/api/flowseeker/outcomes/refresh",
                                     json={"days": days, "horizon": horizon}, headers=headers)
            log.info("pushed refresh signal to :8000 (HTTP %s)", resp.status_code)
        except Exception as e:  # backend down is fine — cache is in Mongo
            log.info("push skipped (backend not reachable): %s", e)

    return {"status": "ok", "alerts": len(alerts), "rules": sorted((stats.get("per_rule") or {}).keys())}


def main() -> None:
    ap = argparse.ArgumentParser(description="Nightly outcome-refresh for the alert ledger")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--horizon", type=int, default=2)
    ap.add_argument("--push", action="store_true", help="also notify a running backend")
    args = ap.parse_args()
    result = asyncio.run(refresh(args.days, args.horizon, args.push))
    log.info("done: %s", result)


if __name__ == "__main__":
    main()
