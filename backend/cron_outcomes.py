#!/usr/bin/env python3
"""
Nightly outcome-refresh trigger for the Tidehunter Pro alert ledger.

Architecture note (2026-09-02): the outcome COMPUTE lives in the running
backend — POST /api/flowseeker/outcomes/refresh — because DuckDBEngine is a
per-process :memory: singleton: the alert ledger (flow_alerts_daily) only
exists inside the server process, so a separate cron process would read its
own empty DB and could never label real alerts. This script therefore just
triggers that endpoint (fail-closed behind X-API-Key, read from the same
.env) and reports the result.

The endpoint writes the precomputed stats + calibration snapshot to Mongo
(flow_outcome_cache), where the morning brief and the Scanner outcome panel
read them.

Run via cron AFTER the market close and after yfinance daily bars settle:
    30 20 * * 1-5  (20:30 ET)

Usage: .venv/bin/python3 cron_outcomes.py [--days 60] [--horizon 2] [--url ...]
Exit codes: 0 = refreshed (or honestly cold), 1 = backend unreachable /
auth rejected / unexpected failure (so cron-mail surfaces real breakage).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cron_outcomes")


def main() -> int:
    ap = argparse.ArgumentParser(description="Trigger in-process outcome refresh on the backend")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--horizon", type=int, default=2)
    ap.add_argument("--url", default="http://localhost:8000",
                    help="backend base URL (default http://localhost:8000)")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    import httpx

    headers = {}
    api_key = os.environ.get("API_SECRET_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        resp = httpx.post(
            f"{args.url.rstrip('/')}/api/flowseeker/outcomes/refresh",
            params={"days": args.days, "horizon": args.horizon},
            headers=headers,
            timeout=120,
        )
    except Exception as e:
        log.error("backend not reachable: %s", e)
        return 1

    if resp.status_code == 401:
        log.error("auth rejected (401) — API_SECRET_KEY missing/mismatched in .env")
        return 1
    if resp.status_code != 200:
        log.error("refresh failed: HTTP %s %s", resp.status_code, resp.text[:200])
        return 1

    body = resp.json()
    status = body.get("status")
    if status == "no_alerts":
        log.info("ledger cold — nothing to refresh (normal until the engine fires)")
        return 0
    log.info("done: %s", body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
