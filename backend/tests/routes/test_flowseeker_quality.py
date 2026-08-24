"""E2E test for GET /api/flowseeker/alerts/quality (v2.x surface contract).

Calls the route function directly (the function is sync — initialised
without `async def` in routes/flowseeker.py) so the test exercises the
real route logic + the real `flow_alerts.alert_quality` SQL + the new
Python-side `is_best_rule` ranking, without standing up ASGI/httpx.

Validates the v2.x per-row contract:
- `wins`              — bit-exact hits (bit-exact path, mirrors frontend)
- `sigma_median`      — DuckDB MEDIAN(sigma) over the window's per-alert
                        sigma values, per (rule, tier); null when no
                        sigma stamp survived the bias filter
- `is_best_rule`      — per-row boolean extracted by Python-side
                        ranking, identical outcome to the frontend's
                        bestRuleForTier with the BEST_RULE_MIN_N=3 floor

None of the prior v2.x suites pins the three above together at the API
contract level. This test is the single source of truth for the expanded
`/alerts/quality` surface.
"""
# Test env must seed BEFORE `routes.flowseeker` import — the module reads
# MONGO_URL/DB_NAME/TESTING at import time via conftest-style globals.
import os
from datetime import UTC, datetime, timezone

import pytest

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_flowseeker_quality")

from routes.flowseeker import institutional_alert_quality  # noqa: E402
from services.duckdb_engine import db as duckdb_engine  # noqa: E402
from services.flow_alerts import init_flow_alert_tables  # noqa: E402


def _seed_rule(engine, tier, rule, hits, total, sigma_mean):
    """Insert `total` rows for (rule, tier); the FIRST `hits` rows meet
    the direction-aware ≥±0.5% move threshold that `alert_quality` counts
    as a win. Sigma values are symmetrically distributed around sigma_mean
    so a DuckDB MEDIAN comes back close to sigma_mean (±half the spread).
    """
    today = datetime.now(UTC).date().isoformat()
    rows = []
    for i in range(total):
        is_hit = i < hits
        # BULLISH bias — hit = move_pct >= 0.5, miss = move_pct < 0.5.
        # The non-hit rows still have move_pct stamped so n_measured ==
        # total rather than total - null_count (matches the real
        # update_moves stamping cadence).
        move_pct = 0.7 if is_hit else -0.2
        sigma = sigma_mean + 0.1 * (i - (total - 1) / 2)
        # key is part of PRIMARY KEY (asof_date, key) — must be non-null and
        # unique per row so executemany doesn't trip the constraint.
        rows.append((today, f"{rule}:{tier}:{i}", rule, tier, "BULLISH", sigma, move_pct))
    engine.execute_write(  # one batch INSERT after the loop builds the rows list

            "INSERT INTO flow_alerts_daily(asof_date, key, rule, tier, bias, sigma, move_pct) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )


@pytest.fixture
def seeded_quality_db():
    """Stage three tiers with deliberately mixed sample sizes so the
    per-row contract has signal at every edge of the algorithm:

    GOLD    — 3 rules (OICONF wins on weighted-hits = 4; SIGMA = 3; SCORE
              n_measured=2 < BEST_RULE_MIN_N=3 floor so it MUST NOT win);
              this is the floor + winner competition test.
    SILVER  — 1 rule (single-rule tier → candidates.len < 2 so
              is_best_rule MUST stay False on every row).
    BRONZE  — 1 rule (same single-rule guard as SILVER).
    """
    init_flow_alert_tables(duckdb_engine)
    duckdb_engine.execute_write("DELETE FROM flow_alerts_daily", None)  # None (not []) routes through plain _conn.execute(sql), not executemany
    _seed_rule(duckdb_engine, "GOLD",   "OICONF", hits=4, total=5, sigma_mean=2.5)
    _seed_rule(duckdb_engine, "GOLD",   "SIGMA",  hits=3, total=4, sigma_mean=3.0)
    _seed_rule(duckdb_engine, "GOLD",   "SCORE",  hits=1, total=2, sigma_mean=1.8)
    _seed_rule(duckdb_engine, "SILVER", "OICONF", hits=2, total=4, sigma_mean=2.0)
    _seed_rule(duckdb_engine, "BRONZE", "SCORE",  hits=1, total=3, sigma_mean=1.5)
    yield
    duckdb_engine.execute_write("DELETE FROM flow_alerts_daily", None)  # None (not []) routes through plain _conn.execute(sql), not executemany


@pytest.mark.asyncio
async def test_alerts_quality_v2x_per_row_surface(seeded_quality_db):
    """E2E assertion that GET /api/flowseeker/alerts/quality surfaces
    wins + sigma_median + is_best_rule on every (rule, tier) row.
    (Route went async with Blademap v3 conviction_calibration.)"""
    body = await institutional_alert_quality(days="30")
    assert "error" not in body, f"route returned error: {body.get('error')}"
    rows = body.get("quality") or (
        body.get("quality_windows", {}).get("30") or
        []
    )
    tiers = {row.get("tier") for row in rows}
    assert {"GOLD", "SILVER", "BRONZE"}.issubset(tiers), tiers

    # Per-row v2.x fields present on EVERY row.
    for row in rows:
        assert "wins"              in row, f"missing wins on {row}"
        assert "sigma_median"      in row, f"missing sigma_median on {row}"
        assert "is_best_rule"      in row, f"missing is_best_rule on {row}"
        # Type + truth-shape guards.
        assert isinstance(row["wins"], (int, float)), row
        assert isinstance(row["is_best_rule"], bool),  row

    # GOLD ranking pinned by the floor + weighted-hits contract.
    gold_rows = [r for r in rows if r["tier"] == "GOLD"]
    gold_best = [r for r in gold_rows if r["is_best_rule"]]
    assert len(gold_best) == 1, f"expected exactly one GOLD winner, got {gold_best}"

    oiconf = next(r for r in gold_rows if r["rule"] == "OICONF")
    sigma  = next(r for r in gold_rows if r["rule"] == "SIGMA")
    score  = next(r for r in gold_rows if r["rule"] == "SCORE")

    # OICONF wins on weighted-hits (4) over SIGMA (3).
    assert oiconf["is_best_rule"] is True
    assert oiconf["wins"] == 4
    assert sigma["is_best_rule"] is False
    assert sigma["wins"] == 3
    # SCORE has n_measured=2 < BEST_RULE_MIN_N=3 → MUST stay False even
    # though it's the only rule under the floor boundary in our fixture.
    assert score["is_best_rule"] is False
    assert score["is_best_rule"] is False, (
        "SCORE (n_measured=2) must NOT win under BEST_RULE_MIN_N=3"
    )

    # MEDIAN(sigma) per row mirrors our seeded sigma_mean to within ±0.2
    # (staged symmetric values around sigma_mean; rounding & row count).
    assert oiconf["sigma_median"] is not None
    assert abs(oiconf["sigma_median"] - 2.5) <= 0.2
    assert sigma["sigma_median"]  is not None
    assert abs(sigma["sigma_median"]  - 3.0) <= 0.2

    # SILVER + BRONZE are single-rule tiers → candidates.len < 2 →
    # is_best_rule MUST be False on every row regardless of ws.
    for row in rows:
        if row["tier"] in ("SILVER", "BRONZE"):
            assert row["is_best_rule"] is False, (
                f"single-rule tier {row['tier']} - {row['rule']} should not "
                "carry is_best_rule=True"
            )


@pytest.mark.asyncio
async def test_alerts_quality_gold_floor_single_tier_demotes_to_false(seeded_quality_db):
    """Separate single-purpose test: when GOLD has only ONE rule, even if
    that rule is well-measured, is_best_rule MUST be False. Catches a
    regression where the MIN_N=3 floor is applied but the candidates<2
    guard is dropped (the dual guard from the frontend)."""
    init_flow_alert_tables(duckdb_engine)
    duckdb_engine.execute_write("DELETE FROM flow_alerts_daily", None)  # None (not []) routes through plain _conn.execute(sql), not executemany
    # Single GOLD rule, well-measured (n_measured=10), perfect hit_rate.
    _seed_rule(duckdb_engine, "GOLD", "OICONF", hits=10, total=10, sigma_mean=2.0)

    body = await institutional_alert_quality(days="30")
    rows = body.get("quality") or []
    gold_rows = [r for r in rows if r["tier"] == "GOLD"]
    assert len(gold_rows) == 1
    assert gold_rows[0]["wins"] == 10
    # Single-rule tier → no comparative signal → is_best_rule False even
    # though the rule itself passes the MIN_N=3 floor.
    assert gold_rows[0]["is_best_rule"] is False, (
        "single-rule GOLD must not flag is_best_rule=True (no comparative "
        "signal even with strong floor qualification)"
    )

# ----------------------------------------------------------------------
# nit-fix from reviewer pass on v2.5: regression pin for the
# _MAX_TRACKED_ENDPOINTS cardinality cap. Without this test, a future
# refactor that drops the cap silently turns the backend into an OOM
# waiting game under pathologically diverse route lists (e.g. random UUID
# suffixes). Seeding 300 distinct endpoints must cap _metrics at 256.
# ----------------------------------------------------------------------
def test_performance_monitor_cardinality_cap():
    from error_tracking import perf_monitor
    perf_monitor._metrics.clear()  # isolate from other tests' state
    for i in range(perf_monitor._MAX_TRACKED_ENDPOINTS + 44):  # 300
        perf_monitor.record(f"GET /endpoint/{i}", 1.0)
    assert len(perf_monitor._metrics) <= perf_monitor._MAX_TRACKED_ENDPOINTS, (
        "cardinality cap regression: _MAX_TRACKED_ENDPOINTS cap must hold (was 256, would be OOM otherwise)"
    )
