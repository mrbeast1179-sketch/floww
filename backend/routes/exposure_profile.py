"""
backend/routes/exposure_profile.py

Sidecar APIRouter for Steal-List #6 — SqueezeMetrics Spot-Shifted
==================================================================

Exposes ``GET /api/exposure_profile/{ticker}`` on the canonical :8000
backend, fed by ``backend/services/squeeze_exposure_profile.py``. This
is a TRUE sidecar — separate routes module mounted via
``app.include_router(routes.exposure_profile.router)`` from
``backend/server.py`` — keeping the chain_consensus / strike_cone /
risk_neutral_density route defs in ``routes/steal_three.py`` uncluttered
AND giving the .md's "sidecar → server.py mount → strike" pattern a
clean rehearsal point.

Query params
------------
* ``shifts``    comma-separated percent shifts, default ``-5,-2,0,2,5``.
* ``accumulate`` if true, UPSERT the response into floww_squeeze_exposure_daily.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter()


_DEFAULT_SHIFTS = (-5.0, -2.0, 0.0, 2.0, 5.0)


def _parse_shifts(raw: str) -> list[float]:
    out: list[float] = []
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            v = float(tok)
            out.append(v)
        except ValueError:
            logger.warning("exposure_profile: bad shifts token %r — skipped", tok)
    if not out:
        return list(_DEFAULT_SHIFTS)
    return out


@router.get("/api/exposure_profile/{ticker}")
def exposure_profile_endpoint(
    ticker: str,
    shifts: str = Query(
        "-5,-2,0,2,5",
        description=(
            "Comma-separated percent spot-shifts (e.g. ``-5,-2,0,2,5`` or "
            "``-3,0,7``). Each value is recomputed as a hypothetical new spot "
            "and exposed as a row in the profile."
        ),
    ),
    accumulate: bool = Query(
        False,
        description=(
            "When true, UPSERT each profile row into "
            "``floww_squeeze_exposure_daily`` keyed on "
            "(snapshot_date, ticker, shift_pct). Idempotent."
        ),
    ),
) -> dict[str, Any]:
    """Compute + (optionally) persist the spot-shifted exposure profile."""
    parsed_shifts = _parse_shifts(shifts)
    try:
        # Lazy imports — avoid the routes -> server -> app include_router
        # circular import at module-load time (routes are imported before
        # server.py finishes building `app`).
        from server import fetch_spot_and_chains
        from services import squeeze_exposure_profile
        from services import duckdb_engine

        raw = fetch_spot_and_chains(ticker.upper(), max_expiries=4)
        spot = float(raw.get("spot", 0.0) or 0.0)
        contracts = raw.get("contracts") or raw.get("calls") or raw.get("chain") or []

        # 30-day approximation if T is unspecified — same convention as
        # strike_cone / risk_neutral_density routes use.
        T = 30.0 / 365.0
        out = squeeze_exposure_profile.compute_spot_shifted_exposure_profile(
            chain=contracts,
            spot=spot,
            T=T,
            shifts_pct=tuple(parsed_shifts),
        )
        out["ticker"] = ticker.upper()

        if accumulate and out.get("profile"):
            try:
                duckdb_engine_obj = getattr(duckdb_engine, "db", duckdb_engine)
                squeeze_exposure_profile.init_exposure_profile_table(
                    duckdb_engine_obj,
                )
                squeeze_exposure_profile.persist_daily(
                    duckdb_engine_obj,
                    ticker.upper(),
                    out,
                    snapshot_date=datetime.now(timezone.utc).date(),
                )
            except Exception as exc:    # pragma: no cover (defensive path)
                logger.warning(
                    "exposure_profile accumulate failed for %s: %s",
                    ticker, exc,
                )
                out.setdefault("warnings", []).append(
                    f"accumulate warning: {type(exc).__name__}: {exc}"
                )

        return out

    except Exception as exc:    # pragma: no cover (defensive degrade)
        logger.warning("exposure_profile endpoint exception: %s", exc)
        return {
            "ticker": ticker.upper(),
            "spot": 0.0,
            "shifts_pct": parsed_shifts,
            "current_total_exposure": 0.0,
            "profile": [],
            "warnings": [f"engine exception: {type(exc).__name__}: {exc}"],
            "method": "bs_reprice_then_dollar_gex",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }


__all__ = ["router"]
